from dataclasses import dataclass
from typing import Optional
import datetime
from datetime import date
from ..config import TIME_SLOTS

@dataclass
class ScheduledTask:
    """
    Represents a scheduled production step assignment.
    
    Attributes:
    -----------
    station_id : str
        Which station is used
    day : datetime.date
        When the task is scheduled
    purchase_order_id : str
        Associated PurchaseOrder ID
    step_id : str
        Which ProductionStep is being executed
    employee_id : Optional[str]
        Assigned employee (if any)
    station_activity : str
        Description of the task
    time_slot: str
        Time slot of the task
    percent_complete: float
        Track completion percentage
    activity_id: str
        Activity tracking
    units_start: int
        Starting unit number
    units_end: int
        Ending unit number
    """
    station_id: str
    day: date
    time_slot: str
    purchase_order_id: str
    step_id: str
    activity_id: str
    employee_id: Optional[str] = None
    percent_complete: float = 0.0
    units_start: int = 1
    units_end: int = 1
    
    def __post_init__(self):
        if self.time_slot not in TIME_SLOTS:
            raise ValueError(f"Invalid time_slot: {self.time_slot}. Must be one of {TIME_SLOTS}") 