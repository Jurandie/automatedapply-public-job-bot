"""ATS adapters."""

from app.application.adapters.ashby import AshbyAdapter
from app.application.adapters.generic_form import GenericFormAdapter
from app.application.adapters.greenhouse import GreenhouseAdapter
from app.application.adapters.lever import LeverAdapter

ADAPTERS = [GreenhouseAdapter(), LeverAdapter(), AshbyAdapter(), GenericFormAdapter()]

