from typing import List, Tuple, Dict
import json
from crewai import Task, Crew
from .base_agent import BaseAgent
from ..models.scheduled_task import ScheduledTask
from ..models.production_step import ProductionStep
from ..models.employee import Employee
from ..config import STATIONS_PER_DAY, WORKERS_PER_STATION, MAX_WORKER_TASKS_PER_DAY
from datetime import date

class ConstraintsAgent(BaseAgent):
    """
    Agent responsible for validating schedule feasibility against constraints.
    """
    
    def __init__(self):
        super().__init__(
            name="Constraints Validator",
            role="Scheduling Constraints Expert",
            goal="Ensure all scheduling constraints are satisfied",
            backstory="""
            Expert in analyzing complex scheduling constraints and dependencies.
            Only reports actual violations of scheduling rules, focusing on:
            - Station double-bookings (same station, same day)
            - Employee availability conflicts
            - Dependency violations (dependent steps scheduled before prerequisites)
            """
        )
    
    def check_feasibility(self,
                         tasks: List[ScheduledTask],
                         steps: List[ProductionStep],
                         employees: List[Employee],
                         previous_reasoning: List[str] = None) -> Tuple[bool, List[Dict]]:
        """Check schedule feasibility with comprehensive constraint checking."""
        
        violations = []
        
        # Group tasks for efficient checking
        tasks_by_day = {}  # day -> List[tasks]
        tasks_by_worker = {}  # (worker_id, day) -> List[tasks]
        tasks_by_station = {}  # (station_id, day) -> List[tasks]
        tasks_by_step = {}  # step_id -> List[tasks]
        
        for task in tasks:
            # By day
            if task.day not in tasks_by_day:
                tasks_by_day[task.day] = []
            tasks_by_day[task.day].append(task)
            
            # By worker
            if task.employee_id:
                key = (task.employee_id, task.day)
                if key not in tasks_by_worker:
                    tasks_by_worker[key] = []
                tasks_by_worker[key].append(task)
            
            # By station
            key = (task.station_id, task.day)
            if key not in tasks_by_station:
                tasks_by_station[key] = []
            tasks_by_station[key].append(task)
            
            # By step
            if task.step_id not in tasks_by_step:
                tasks_by_step[task.step_id] = []
            tasks_by_step[task.step_id].append(task)
        
        # 1. Check worker availability and skills
        for (worker_id, day), worker_tasks in tasks_by_worker.items():
            worker = next(e for e in employees if e.id == worker_id)
            
            # Check availability
            if day not in worker.availability:
                violations.append({
                    'type': 'employee_unavailable',
                    'employee_id': worker_id,
                    'day': day,
                    'severity': 'high'
                })
            
            # Check skills
            for task in worker_tasks:
                step = next(s for s in steps if s.step_id == task.step_id)
                if step.activity_id not in worker.skills:
                    violations.append({
                        'type': 'skill_mismatch',
                        'employee_id': worker_id,
                        'step_id': task.step_id,
                        'activity_id': step.activity_id,
                        'severity': 'high'
                    })
        
        # 2. Check worker load constraints - ONLY check shifts per day, not processing time
        for (worker_id, day), worker_tasks in tasks_by_worker.items():
            # Check shift limits
            shifts = set(t.time_slot for t in worker_tasks)
            if len(shifts) > 2:
                violations.append({
                    'type': 'worker_overload',
                    'employee_id': worker_id,
                    'day': day,
                    'shifts': list(shifts),
                    'severity': 'medium'
                })
        
        # 3. Check station constraints
        for (station_id, day), station_tasks in tasks_by_station.items():
            # Check for conflicts
            am_tasks = [t for t in station_tasks if t.time_slot == 'AM']
            pm_tasks = [t for t in station_tasks if t.time_slot == 'PM']
            
            if len(am_tasks) > 1 or len(pm_tasks) > 1:
                violations.append({
                    'type': 'station_conflict',
                    'station_id': station_id,
                    'day': day,
                    'severity': 'high'
                })
        
        # 4. Check dependencies and unit progression
        for step in steps:
            if step.step_id not in tasks_by_step:
                continue
                
            step_tasks = sorted(tasks_by_step[step.step_id], 
                              key=lambda t: (t.day, t.time_slot == 'PM'))
            
            # Check dependency completion
            for dep_id in step.depends_on:
                if dep_id not in tasks_by_step:
                    violations.append({
                        'type': 'missing_dependency',
                        'step_id': step.step_id,
                        'dependency_id': dep_id,
                        'severity': 'high'
                    })
                    continue
                
                dep_tasks = tasks_by_step[dep_id]
                dep_units = set()
                for dt in dep_tasks:
                    dep_units.update(range(dt.units_start, dt.units_end + 1))
                
                # Check minimum units before starting
                first_task = step_tasks[0]
                if len(dep_units) < step.min_units_to_start:
                    violations.append({
                        'type': 'insufficient_units',
                        'step_id': step.step_id,
                        'dependency_id': dep_id,
                        'units_available': len(dep_units),
                        'units_needed': step.min_units_to_start,
                        'severity': 'high'
                    })
        
        # Classify overall feasibility
        high_severity_count = sum(1 for v in violations if v['severity'] == 'high')
        medium_severity_count = sum(1 for v in violations if v['severity'] == 'medium')
        
        is_feasible = (
            high_severity_count == 0 and
            medium_severity_count <= 2  # Allow some medium violations
        )
        
        return is_feasible, violations
    
    def _calculate_time_diff(self, day1: date, slot1: str, day2: date, slot2: str) -> float:
        """Calculate time difference in days between two time slots."""
        days = (day2 - day1).days
        if slot1 == slot2:
            return days
        elif slot2 == "PM":  # slot1 is AM
            return days + 0.5
        else:  # slot1 is PM, slot2 is AM
            return days - 0.5
    
    def _format_tasks(self, tasks: List[ScheduledTask]) -> str:
        return "\n".join([
            f"- Task {task.step_id}: Station={task.station_id}, "
            f"Day={task.day}, Employee={task.employee_id}"
            for task in tasks
        ])
    
    def _format_steps(self, steps: List[ProductionStep]) -> str:
        return "\n".join([
            f"- Step {step.step_id}: Station={step.station_id}, "
            f"Dependencies={step.depends_on}"
            for step in steps
        ])
    
    def _format_employees(self, employees: List[Employee]) -> str:
        return "\n".join([
            f"- {emp.name} (ID={emp.id}): Available on {emp.availability}"
            for emp in employees
        ])

    def _format_previous_violations(self) -> str:
        # Implementation of _format_previous_violations method
        # This method should return a formatted string representing previous violations
        # For now, we'll return an empty string
        return "" 

    def _check_employee_shift_limits(self, 
                                   scheduled_tasks: List[ScheduledTask],
                                   employees: List[Employee]) -> List[Dict]:
        """Check employee shift limits and availability."""
        violations = []
        employee_shifts = {}  # (employee_id, day) -> List[time_slot]
        
        for task in scheduled_tasks:
            if task.employee_id:
                key = (task.employee_id, task.day)
                if key not in employee_shifts:
                    employee_shifts[key] = []
                employee_shifts[key].append(task.time_slot)
                
                # Check if employee is available for this shift
                employee = next((e for e in employees if e.id == task.employee_id), None)
                if employee and not employee.is_available(task.day, task.time_slot):
                    violations.append({
                        'type': 'employee_shift_unavailable',
                        'step_id': task.step_id,
                        'employee_id': task.employee_id,
                        'day': task.day,
                        'time_slot': task.time_slot,
                        'description': f"Employee {task.employee_id} is not available for {task.time_slot} shift on {task.day}"
                    })
                
                # Check shift count per day
                if len(employee_shifts[key]) > employee.max_shifts_per_day:
                    violations.append({
                        'type': 'employee_shift_limit',
                        'step_id': task.step_id,
                        'employee_id': task.employee_id,
                        'day': task.day,
                        'time_slot': task.time_slot,
                        'description': f"Employee {task.employee_id} exceeds max shifts ({employee.max_shifts_per_day}) on {task.day}"
                    })
        
        return violations

    def _check_worker_load(self, worker_tasks: List[ScheduledTask], steps: List[ProductionStep]) -> List[Dict]:
        """Check worker load constraints."""
        violations = []
        
        # Group by day and shift
        by_shift = {}  # (day, shift) -> List[tasks]
        for task in worker_tasks:
            key = (task.day, task.time_slot)
            if key not in by_shift:
                by_shift[key] = []
            by_shift[key].append(task)
        
        # Check each shift
        for (day, shift), tasks in by_shift.items():
            total_time = sum(
                (t.units_end - t.units_start + 1) *
                next(s.duration_days for s in steps if s.step_id == t.step_id)
                for t in tasks
            )
            
            # Round up to nearest shift (0.5 days)
            shifts_needed = (total_time + 0.49) // 0.5
            
            # Only violate if we need more than one shift
            if shifts_needed > 1:
                violations.append({
                    'type': 'worker_overload',
                    'employee_id': tasks[0].employee_id,
                    'day': day,
                    'shift': shift,
                    'time': total_time,
                    'shifts_needed': shifts_needed,
                    'severity': 'high'
                })
        
        return violations 