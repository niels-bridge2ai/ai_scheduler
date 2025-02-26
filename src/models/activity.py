from dataclasses import dataclass

@dataclass
class Activity:
    """
    Represents a type of work or skill (e.g. "Welding").
    
    Attributes:
    -----------
    id : str
        Unique identifier for this activity (e.g. "A1").
    description : str
        Human-readable description (e.g. "Welding").
    """
    id: str
    description: str

    def __repr__(self):
        return f"<Activity {self.id}: {self.description}>" 