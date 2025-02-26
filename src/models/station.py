from dataclasses import dataclass
from typing import Optional

@dataclass
class Station:
    """
    Represents a production station that can perform different activities.
    
    Attributes:
    -----------
    id : str
        Unique station identifier
    current_activity_id : Optional[str]
        ID of the activity currently set up on this station (if any)
    """
    id: str
    current_activity_id: Optional[str] = None

    def __repr__(self):
        return f"<Station {self.id}>" 