from typing import List, Dict, Set, Optional
import json
from crewai import Task, Crew
from .base_agent import BaseAgent
from ..models.employee import Employee
from ..models.scheduled_task import ScheduledTask
from ..models.production_step import ProductionStep
from ..models.locked_assignment import LockedAssignment
from ..config import STATIONS_PER_DAY, WORKERS_PER_STATION, MAX_WORKER_TASKS_PER_DAY
import datetime

class ResourceAssigner(BaseAgent):
    """
    Agent responsible for matching employees to scheduled tasks based on skills and availability.
    """
    
    def __init__(self, employees: List[Employee]):
        super().__init__(
            name="Resource Manager",
            role="Resource Allocation Specialist",
            goal="Optimize employee assignments to tasks based on skills and availability",
            backstory="""
            Expert in workforce management and skill-based task assignment.
            Ensures optimal matching of employees to tasks while considering
            their skills, availability, and workload balance.
            """
        )
        self.employees = employees
        self.current_tasks = []  # Track current assignments
        self.production_steps = None  # Will be set during assign_resources
    
    def assign_resources(self,
                        scheduled_tasks: List[ScheduledTask],
                        production_steps: List[ProductionStep],
                        locked_assignments: Set[LockedAssignment] = None,
                        previous_violations: List[Dict] = None,
                        previous_reasoning: str = None) -> None:
        """Assign resources using skill-based matching and workload balancing."""
        
        if not self.employees:
            raise ValueError("No employees available for assignment")
            
        # Store production steps for load calculations
        self.production_steps = production_steps

        # Validate employee skills
        for emp in self.employees:
            if not emp.skills:
                raise ValueError(f"Employee {emp.id} has no skills assigned")

        # Group tasks by activity for better assignment
        activity_tasks = {}  # activity_id -> List[tasks]
        for task in scheduled_tasks:
            step = next(s for s in production_steps if s.step_id == task.step_id)
            if not step.activity_id:
                raise ValueError(f"Task {task.step_id} has no activity")
                
            if step.activity_id not in activity_tasks:
                activity_tasks[step.activity_id] = []
            activity_tasks[step.activity_id].append(task)

        # Assign workers by activity
        for activity_id, tasks in activity_tasks.items():
            # Get qualified workers
            qualified_workers = [
                emp for emp in self.employees 
                if activity_id in emp.skills
            ]
            
            if not qualified_workers:
                raise ValueError(f"No qualified workers for activity {activity_id}")

            # Assign workers to tasks
            for task in tasks:
                if not task.employee_id:  # Only assign if not already assigned
                    # Find least loaded qualified worker
                    best_worker = min(
                        qualified_workers,
                        key=lambda w: self._get_worker_load(w.id, task.day, task.time_slot, scheduled_tasks)
                    )
                    task.employee_id = best_worker.id
    
    def _format_employees(self, employees: List[Employee]) -> str:
        return "\n".join([
            f"- {emp.name} (ID={emp.id}): Skills={emp.skills}, "
            f"Available={emp.availability} (both AM/PM shifts)"
            for emp in employees
        ])
    
    def _format_tasks_and_steps(self, tasks: List[ScheduledTask], steps: List[ProductionStep]) -> str:
        step_map = {s.step_id: s for s in steps}
        
        # Group tasks by day and shift
        day_shift_tasks = {}  # (day, shift) -> List[tasks]
        for task in tasks:
            key = (task.day, task.time_slot)
            if key not in day_shift_tasks:
                day_shift_tasks[key] = []
            day_shift_tasks[key].append(task)
        
        formatted = []
        for (day, shift), shift_tasks in sorted(day_shift_tasks.items()):
            formatted.append(f"\nDay {day} - {shift} Shift:")
            for task in shift_tasks:
                step = step_map.get(task.step_id)
                activity = step.activity_id if step else "Unknown"
                formatted.append(
                    f"  - Task {task.step_id}: Station={task.station_id}, "
                    f"Activity={activity}"
                )
        
        return "\n".join(formatted)
    
    def _format_locked_assignments(self, assignments: Set[LockedAssignment]) -> str:
        return "\n".join([
            f"- Task {assignment.step_id} must use employee {assignment.employee_id}"
            for assignment in assignments
        ])
    
    def _format_station_activities(self, tasks: List[ScheduledTask], steps: List[ProductionStep]) -> str:
        """Format station activity assignments."""
        activities = {}  # (station_id, day) -> List[(time_slot, activity_id)]
        
        for task in sorted(tasks, key=lambda t: (t.day, t.time_slot)):
            step = next((s for s in steps if s.step_id == task.step_id), None)
            if step:
                key = (task.station_id, task.day)
                if key not in activities:
                    activities[key] = []
                activities[key].append((task.time_slot, step.activity_id))
        
        return "\n".join(
            f"Station {station_id} on {day}: " + 
            ", ".join(f"{slot}: {activity}" for slot, activity in day_activities)
            for (station_id, day), day_activities in sorted(activities.items())
        )
    
    def _analyze_schedule_quality(self, scheduled_tasks: List[ScheduledTask]) -> str:
        """Analyze schedule quality metrics."""
        # Track employee workload
        employee_shifts = {}  # employee_id -> count of shifts
        station_assignments = {}  # employee_id -> set of stations
        
        for task in scheduled_tasks:
            if task.employee_id:
                if task.employee_id not in employee_shifts:
                    employee_shifts[task.employee_id] = 0
                    station_assignments[task.employee_id] = set()
                employee_shifts[task.employee_id] += 1
                station_assignments[task.employee_id].add(task.station_id)
        
        # Calculate metrics
        avg_shifts = sum(employee_shifts.values()) / len(employee_shifts) if employee_shifts else 0
        avg_stations = sum(len(stations) for stations in station_assignments.values()) / len(station_assignments) if station_assignments else 0
        
        return f"""
        Resource Utilization Analysis:
        - Average shifts per worker: {avg_shifts:.1f}
        - Average stations per worker: {avg_stations:.1f}
        - Workers assigned: {len(employee_shifts)}
        - Most utilized worker: {max(employee_shifts.values()) if employee_shifts else 0} shifts
        - Least utilized worker: {min(employee_shifts.values()) if employee_shifts else 0} shifts
        """
    
    def _format_shift_usage(self, tasks: List[ScheduledTask]) -> str:
        shift_usage = {}
        for task in tasks:
            key = (task.day, task.time_slot)
            if key not in shift_usage:
                shift_usage[key] = 0
            shift_usage[key] += 1
        
        return "\n".join(
            f"- {day} {shift}: {count}/12 stations"
            for (day, shift), count in sorted(shift_usage.items())
        )

    def _format_unit_requirements(self, tasks: List[ScheduledTask], steps: List[ProductionStep]) -> str:
        requirements = []
        
        # Group by shift
        shift_tasks = {}  # (day, slot) -> List[tasks]
        for task in sorted(tasks, key=lambda t: (t.day, t.time_slot)):
            key = (task.day, task.time_slot)
            if key not in shift_tasks:
                shift_tasks[key] = []
            shift_tasks[key].append(task)
        
        for (day, slot), tasks in shift_tasks.items():
            requirements.append(f"\n{day} {slot} Shift:")
            for task in tasks:
                step = next((s for s in steps if s.step_id == task.step_id), None)
                if step:
                    requirements.append(
                        f"- Station {task.station_id}: "
                        f"Processing units {task.units_start}-{task.units_end} "
                        f"of Step {task.step_id} "
                        f"(Activity {step.activity_id}, {step.duration_days:.1f} days/unit)"
                    )
        
        return "\n".join(requirements)

    def _analyze_worker_loads(self, tasks: List[ScheduledTask], employees: List[Employee]) -> str:
        loads = []
        
        # Calculate processing time per worker per shift
        worker_times = {}  # (worker_id, day, slot) -> total_processing_time
        for task in tasks:
            if task.employee_id:
                key = (task.employee_id, task.day, task.time_slot)
                if key not in worker_times:
                    worker_times[key] = 0
                units = task.units_end - task.units_start + 1
                step = next((s for s in self.production_steps if s.step_id == task.step_id), None)
                if step:
                    worker_times[key] += units * step.duration_days
        
        # Format load analysis
        for emp in employees:
            emp_loads = [
                (day, slot, time)
                for (worker_id, day, slot), time in worker_times.items()
                if worker_id == emp.id
            ]
            if emp_loads:
                avg_load = sum(time for _, _, time in emp_loads) / len(emp_loads)
                loads.append(
                    f"\n{emp.name} (ID={emp.id}):"
                    f"- Average load: {avg_load:.1f} days/shift"
                    f"- Skills: {emp.skills}"
                    f"- Current assignments: {len(emp_loads)} shifts"
                )
        
        return "\n".join(loads)

    def _check_worker_capacity(self, worker_id: str, day: datetime.date, slot: str,
                             new_units: int, step: ProductionStep) -> bool:
        """Check if worker has capacity for additional units."""
        current_time = 0
        for task in self.current_tasks:
            if (task.employee_id == worker_id and 
                task.day == day and 
                task.time_slot == slot):
                units = task.units_end - task.units_start + 1
                task_step = next(s for s in self.production_steps if s.step_id == task.step_id)
                current_time += units * task_step.duration_days
        
        new_time = new_units * step.duration_days
        return (current_time + new_time) <= 0.5  # Half day per shift

    def _find_available_worker(self, step: ProductionStep, day: datetime.date, 
                             time_slot: str, units: int) -> Optional[str]:
        """Find a worker with capacity who has the required skills."""
        processing_time = units * step.duration_days
        
        # Find qualified workers
        qualified_workers = [
            emp for emp in self.employees
            if step.activity_id in emp.skills
            and day in emp.availability
        ]
        
        # Sort by current load (prefer less loaded workers)
        worker_loads = {}
        for worker in qualified_workers:
            key = (worker.id, day, time_slot)
            current_load = sum(
                (t.units_end - t.units_start + 1) * 
                next(s.duration_days for s in self.production_steps if s.step_id == t.step_id)
                for t in self.current_tasks
                if t.employee_id == worker.id and t.day == day and t.time_slot == time_slot
            )
            worker_loads[worker.id] = current_load
        
        # Sort workers by load
        qualified_workers.sort(key=lambda w: worker_loads[w.id])
        
        # Find first worker with capacity
        for worker in qualified_workers:
            if worker_loads[worker.id] + processing_time <= 0.5:
                return worker.id 

    def _get_worker_load(self, worker_id: str, day: datetime.date, time_slot: str, 
                        scheduled_tasks: List[ScheduledTask]) -> float:
        """Calculate worker's current load for a specific shift."""
        current_load = 0.0
        
        # Sum up processing time for all tasks assigned to this worker in this shift
        for task in scheduled_tasks:
            if (task.employee_id == worker_id and 
                task.day == day and 
                task.time_slot == time_slot):
                # Get step info to calculate processing time
                step = next(s for s in self.production_steps if s.step_id == task.step_id)
                units = task.units_end - task.units_start + 1
                current_load += units * step.duration_days
        
        return current_load 