from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class ProductionStep:
    """
    Represents a single step in the manufacturing/production pipeline.
    
    Attributes:
    -----------
    step_id : str
        Unique identifier for this step
    purchase_order_id : str
        The ID of the PurchaseOrder this step belongs to
    activity_id : str
        The ID of the Activity (skill) required to perform this step
    step_order : int
        The step's position in the sequence (1, 2, 3, ...)
    duration_days : float
        How many days this step requires (time per unit)
    setup_time_days : float
        Additional setup time needed before starting
    teardown_time_days : float
        Additional cleanup time after completion
    units_per_station : int
        How many units can be processed in parallel on one station
    min_units_to_start : int
        How many units must complete previous step before this can start
    depends_on : List[str]
        List of step_ids that must be completed before this step
    percent_complete : float
        Percentage of completion for this step
    """
    step_id: str
    purchase_order_id: str
    activity_id: str
    step_order: int
    duration_days: float
    setup_time_days: float
    teardown_time_days: float
    units_per_station: int = 1
    min_units_to_start: int = 1
    depends_on: List[str] = field(default_factory=list)
    percent_complete: float = 0.0

    def __post_init__(self):
        if self.depends_on is None:
            self.depends_on = [] 