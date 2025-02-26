from crewai import Agent, Task
from ..config import config, TIME_SLOTS
from typing import List, Dict
from ..models.scheduled_task import ScheduledTask

class BaseAgent:
    """Base class for AI-powered agents using CrewAI."""
    
    def __init__(self, name: str, role: str, goal: str, backstory: str = None):
        if not config.validate():
            raise ValueError("Missing required API keys in environment variables")
            
        self.agent = Agent(
            name=name,
            role=role,
            goal=goal,
            backstory=backstory or f"An AI agent specialized in {role.lower()} for production scheduling",
            allow_delegation=True,
            verbose=True,
            llm_config={
                "model": "o3-mini",
                "api_key": config.openai_api_key,
                "temperature": 0.7
            }
        ) 

    def _format_violation_history(self, violations: List[Dict]) -> str:
        if not violations:
            return "No previous violations."
            
        formatted = []
        for record in violations:
            iteration = record['iteration']
            for v in record['violations']:
                time_info = f" ({v.get('time_slot', 'unknown shift')})"
                if v['type'] == 'dependency_violation':
                    formatted.append(
                        f"Iteration {iteration}: Dependency issue - Step {v['step_id']} "
                        f"must wait for {v['related_step_id']} - Day {v['day']}{time_info}"
                    )
                elif v['type'] == 'employee_unavailable':
                    formatted.append(
                        f"Iteration {iteration}: Availability issue - Employee {v['employee_id']} "
                        f"unavailable on {v['day']}{time_info}"
                    )
                elif v['type'] == 'station_conflict':
                    formatted.append(
                        f"Iteration {iteration}: Station conflict - {v['station_id']} "
                        f"overbooked on {v['day']}{time_info}"
                    )
                elif v['type'] == 'worker_overload':
                    formatted.append(
                        f"Iteration {iteration}: Worker overload - {v['employee_id']} "
                        f"has multiple tasks on {v['day']}{time_info}"
                    )
        return "\n".join(formatted)

    def _format_time_slot(self, time_slot: str) -> str:
        """Format time slot for display."""
        return f"{time_slot} shift"
    
    def _get_next_slot(self, current_slot: str) -> str:
        """Get next available time slot."""
        idx = TIME_SLOTS.index(current_slot)
        return TIME_SLOTS[(idx + 1) % len(TIME_SLOTS)]
    
    def _calculate_slot_utilization(self, tasks: List[ScheduledTask]) -> Dict[str, float]:
        """Calculate utilization per shift."""
        total_am = total_pm = 12 * 10  # stations * days
        used_am = used_pm = 0
        
        for task in tasks:
            if task.time_slot == "AM":
                used_am += 1
            else:
                used_pm += 1
                
        return {
            "AM": (used_am / total_am) * 100,
            "PM": (used_pm / total_pm) * 100,
            "Total": (len(tasks) / (total_am + total_pm)) * 100
        } 