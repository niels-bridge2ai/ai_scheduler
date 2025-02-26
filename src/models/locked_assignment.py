from dataclasses import dataclass
from datetime import date

@dataclass(frozen=True)
class LockedAssignment:
    """Represents a locked task assignment that cannot be changed."""
    step_id: str
    station_id: str
    day: date
    time_slot: str  # Add time_slot field
    activity_id: str  # Add activity tracking
    employee_id: str = None  # Optional since not all tasks need workers
    percent_complete: float = 0.0 