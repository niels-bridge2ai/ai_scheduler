from dataclasses import dataclass
from typing import List, Set
from datetime import date

@dataclass
class Employee:
    """
    Represents an employee with activity-based skills and availability.
    
    Attributes:
    -----------
    id : str
        Unique employee ID
    name : str
        Human-readable name
    skills : List[str]
        List of Activity IDs this employee can perform
    availability : Set[date]
        Dates when this employee is available
    am_shift_available : bool
        Whether the employee is available for the AM shift
    pm_shift_available : bool
        Whether the employee is available for the PM shift
    max_shifts_per_day : int
        Maximum number of shifts this employee can work in a day
    """
    id: str
    name: str
    skills: List[str]
    availability: Set[date]
    am_shift_available: bool = True
    pm_shift_available: bool = True
    max_shifts_per_day: int = 2

    def __repr__(self):
        return f"<Employee {self.name} (skills={self.skills})>"

    def is_available(self, day: date, time_slot: str) -> bool:
        """Check if employee is available for a specific day and shift."""
        if day not in self.availability:
            return False
        if time_slot == "AM" and not self.am_shift_available:
            return False
        if time_slot == "PM" and not self.pm_shift_available:
            return False
        return True 