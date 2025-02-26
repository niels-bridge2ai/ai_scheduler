from dataclasses import dataclass
import datetime

@dataclass
class PurchaseOrder:
    """
    Represents a high-level order to fulfill.
    
    Attributes:
    -----------
    id : str
        Unique identifier
    due_date : datetime.date
        When the order needs to be completed
    base_priority : int
        Initial priority (1-100)
    value : float
        Monetary or importance value
    effective_priority : int
        Calculated priority (can be updated by agents)
    units : int
        Number of units to produce
    """
    id: str
    due_date: datetime.date
    base_priority: int
    value: float
    effective_priority: int = None
    units: int = 1  # Number of units to produce

    def __post_init__(self):
        if self.effective_priority is None:
            self.effective_priority = self.base_priority

    def __repr__(self):
        return f"<PO {self.id} (priority={self.effective_priority})>" 