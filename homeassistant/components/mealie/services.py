"""Define services for the Mealie integration."""

from dataclasses import asdict
from datetime import date
from typing import cast

from aiomealie import (
    MealieConnectionError,
    MealieNotFoundError,
    MealieValidationError,
    MealplanEntryType,
)
import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DATE
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_END_DATE,
    ATTR_ENTRY_TYPE,
    ATTR_INCLUDE_TAGS,
    ATTR_NOTE_TEXT,
    ATTR_NOTE_TITLE,
    ATTR_RECIPE_ID,
    ATTR_RESULT_LIMIT,
    ATTR_SEARCH_TERMS,
    ATTR_START_DATE,
    ATTR_URL,
    DOMAIN,
)
from .coordinator import MealieConfigEntry

SERVICE_GET_MEALPLAN = "get_mealplan"
SERVICE_GET_MEALPLAN_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): str,
        vol.Optional(ATTR_START_DATE): cv.date,
        vol.Optional(ATTR_END_DATE): cv.date,
    }
)

SERVICE_GET_RECIPE = "get_recipe"
SERVICE_GET_RECIPE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): str,
        vol.Required(ATTR_RECIPE_ID): str,
    }
)

SERVICE_GET_RECIPES = "get_recipes"
SERVICE_GET_RECIPES_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): str,
        vol.Optional(ATTR_SEARCH_TERMS): str,
        vol.Optional(ATTR_RESULT_LIMIT): int,
    }
)

SERVICE_IMPORT_RECIPE = "import_recipe"
SERVICE_IMPORT_RECIPE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): str,
        vol.Required(ATTR_URL): str,
        vol.Optional(ATTR_INCLUDE_TAGS): bool,
    }
)

SERVICE_SET_RANDOM_MEALPLAN = "set_random_mealplan"
SERVICE_SET_RANDOM_MEALPLAN_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): str,
        vol.Required(ATTR_DATE): cv.date,
        vol.Required(ATTR_ENTRY_TYPE): vol.In([x.lower() for x in MealplanEntryType]),
    }
)

SERVICE_SET_MEALPLAN = "set_mealplan"
SERVICE_SET_MEALPLAN_SCHEMA = vol.Any(
    vol.Schema(
        {
            vol.Required(ATTR_CONFIG_ENTRY_ID): str,
            vol.Required(ATTR_DATE): cv.date,
            vol.Required(ATTR_ENTRY_TYPE): vol.In(
                [x.lower() for x in MealplanEntryType]
            ),
            vol.Required(ATTR_RECIPE_ID): str,
        }
    ),
    vol.Schema(
        {
            vol.Required(ATTR_CONFIG_ENTRY_ID): str,
            vol.Required(ATTR_DATE): cv.date,
            vol.Required(ATTR_ENTRY_TYPE): vol.In(
                [x.lower() for x in MealplanEntryType]
            ),
            vol.Required(ATTR_NOTE_TITLE): str,
            vol.Optional(ATTR_NOTE_TEXT): str,
        }
    ),
)


def _async_get_entry(call: ServiceCall) -> MealieConfigEntry:
    """Get the Mealie config entry."""
    config_entry_id: str = call.data[ATTR_CONFIG_ENTRY_ID]
    if not (entry := call.hass.config_entries.async_get_entry(config_entry_id)):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="integration_not_found",
            translation_placeholders={"target": DOMAIN},
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="not_loaded",
            translation_placeholders={"target": entry.title},
        )
    return cast(MealieConfigEntry, entry)


async def _async_get_mealplan(call: ServiceCall) -> ServiceResponse:
    """Get the mealplan for a specific range."""
    entry = _async_get_entry(call)
    start_date = call.data.get(ATTR_START_DATE, date.today())
    end_date = call.data.get(ATTR_END_DATE, date.today())
    if end_date < start_date:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="end_date_before_start_date",
        )
    client = entry.runtime_data.client
    try:
        mealplans = await client.get_mealplans(start_date, end_date)
    except MealieConnectionError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="connection_error",
        ) from err
    return {"mealplan": [asdict(x) for x in mealplans.items]}


async def _async_get_recipe(call: ServiceCall) -> ServiceResponse:
    """Get a recipe."""
    entry = _async_get_entry(call)
    recipe_id = call.data[ATTR_RECIPE_ID]
    client = entry.runtime_data.client
    try:
        recipe = await client.get_recipe(recipe_id)
    except MealieConnectionError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="connection_error",
        ) from err
    except MealieNotFoundError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="recipe_not_found",
            translation_placeholders={"recipe_id": recipe_id},
        ) from err
    return {"recipe": asdict(recipe)}


async def _async_get_recipes(call: ServiceCall) -> ServiceResponse:
    """Get recipes."""
    entry = _async_get_entry(call)
    search_terms = call.data.get(ATTR_SEARCH_TERMS)
    result_limit = call.data.get(ATTR_RESULT_LIMIT, 10)
    client = entry.runtime_data.client
    try:
        recipes = await client.get_recipes(search=search_terms, per_page=result_limit)
    except MealieConnectionError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="connection_error",
        ) from err
    except MealieNotFoundError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_recipes_found",
        ) from err
    return {"recipes": asdict(recipes)}


async def _async_import_recipe(call: ServiceCall) -> ServiceResponse:
    """Import a recipe."""
    entry = _async_get_entry(call)
    url = call.data[ATTR_URL]
    include_tags = call.data.get(ATTR_INCLUDE_TAGS, False)
    client = entry.runtime_data.client
    try:
        recipe = await client.import_recipe(url, include_tags)
    except MealieValidationError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="could_not_import_recipe",
        ) from err
    except MealieConnectionError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="connection_error",
        ) from err
    if call.return_response:
        return {"recipe": asdict(recipe)}
    return None


async def _async_set_random_mealplan(call: ServiceCall) -> ServiceResponse:
    """Set a random mealplan."""
    entry = _async_get_entry(call)
    mealplan_date = call.data[ATTR_DATE]
    entry_type = MealplanEntryType(call.data[ATTR_ENTRY_TYPE])
    client = entry.runtime_data.client
    try:
        mealplan = await client.random_mealplan(mealplan_date, entry_type)
    except MealieConnectionError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="connection_error",
        ) from err
    if call.return_response:
        return {"mealplan": asdict(mealplan)}
    return None


async def _async_set_mealplan(call: ServiceCall) -> ServiceResponse:
    """Set a mealplan."""
    entry = _async_get_entry(call)
    mealplan_date = call.data[ATTR_DATE]
    entry_type = MealplanEntryType(call.data[ATTR_ENTRY_TYPE])
    client = entry.runtime_data.client
    try:
        mealplan = await client.set_mealplan(
            mealplan_date,
            entry_type,
            recipe_id=call.data.get(ATTR_RECIPE_ID),
            note_title=call.data.get(ATTR_NOTE_TITLE),
            note_text=call.data.get(ATTR_NOTE_TEXT),
        )
    except MealieConnectionError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="connection_error",
        ) from err
    if call.return_response:
        return {"mealplan": asdict(mealplan)}
    return None


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Set up the services for the Mealie integration."""

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_MEALPLAN,
        _async_get_mealplan,
        schema=SERVICE_GET_MEALPLAN_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_RECIPE,
        _async_get_recipe,
        schema=SERVICE_GET_RECIPE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_RECIPES,
        _async_get_recipes,
        schema=SERVICE_GET_RECIPES_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_RECIPE,
        _async_import_recipe,
        schema=SERVICE_IMPORT_RECIPE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_RANDOM_MEALPLAN,
        _async_set_random_mealplan,
        schema=SERVICE_SET_RANDOM_MEALPLAN_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_MEALPLAN,
        _async_set_mealplan,
        schema=SERVICE_SET_MEALPLAN_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
