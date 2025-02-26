from typing import List, Set, Dict
import datetime
from crewai import Task, Crew
from .base_agent import BaseAgent
from ..models.station import Station
from ..models.purchase_order import PurchaseOrder
from ..models.production_step import ProductionStep
from ..models.scheduled_task import ScheduledTask
from ..models.locked_assignment import LockedAssignment
import json
from ..config import STATIONS_PER_DAY

class StepSequencer(BaseAgent):
    """
    Agent responsible for creating initial feasible schedules.
    """
    
    def __init__(self, station_list: List[Station], date_list: List[datetime.date]):
        super().__init__(
            name="Sequence Planner",
            role="Production Sequence Specialist",
            goal="Create optimal production sequences respecting dependencies and station availability",
            backstory="""
            Expert in production planning and scheduling optimization.
            Specializes in creating efficient sequences while considering
            station capacity, dependencies, and priorities.
            """
        )
        self.station_list = station_list
        self.date_list = date_list
        self.production_steps = None  # Will be set during create_schedule
        self.purchase_orders = None  # Will be set during create_schedule
    
    def create_schedule(self,
                       purchase_orders: List[PurchaseOrder],
                       steps: List[ProductionStep],
                       locked_assignments: Set[LockedAssignment] = None,
                       previous_violations: List[Dict] = None,
                       previous_reasoning: str = None) -> List[ScheduledTask]:
        """Create schedule with parallel PO processing."""
        
        self.production_steps = steps
        self.purchase_orders = purchase_orders  # Store purchase orders
        station_states = {s.id: s.current_activity_id for s in self.station_list}
        
        # Track progress per PO - moved outside day loop to persist across days
        completed_units = {}  # step_id -> set(completed units)
        scheduled_tasks = []

        for current_day in self.date_list:
            for time_slot in ["AM", "PM"]:
                scheduled_this_shift = set()  # stations used
                in_progress_units = {}  # step_id -> set(units being processed this shift)
                
                # Find available work across ALL POs
                available_work = []
                
                # Check each PO for available work
                for po in purchase_orders:
                    steps_for_po = [s for s in steps if s.purchase_order_id == po.id]
                    
                    for step in steps_for_po:
                        # Skip if step is complete
                        if self._is_step_complete(step, po, completed_units):
                            continue
                            
                        # Check step's dependencies
                        if self._can_start_step(step, completed_units):
                            # Calculate available units
                            available_units = self._get_available_units(
                                step, po, completed_units, in_progress_units
                            )
                            if available_units:
                                available_work.append((step, po, available_units))

                # Schedule work across available stations
                while len(scheduled_this_shift) < STATIONS_PER_DAY and available_work:
                    # Score all available work
                    scored_work = []
                    for work in available_work:
                        step, po, units = work
                        score = self._calculate_step_score(step, po, completed_units)
                        scored_work.append((score, step, po, units))  # Include score in tuple
                    
                    # Sort by score (first element of tuple)
                    scored_work.sort(key=lambda x: x[0], reverse=True)
                    
                    # Schedule highest scoring work
                    for score, step, po, units in scored_work:  # Unpack all elements
                        # Find suitable station
                        best_station, needs_setup = self._find_best_station(
                            step, station_states, scheduled_this_shift
                        )
                        
                        if best_station:
                            task = ScheduledTask(
                                step_id=step.step_id,
                                purchase_order_id=po.id,
                                station_id=best_station,
                                activity_id=step.activity_id,
                                day=current_day,
                                time_slot=time_slot,
                                units_start=min(units),
                                units_end=max(units)
                            )
                            
                            scheduled_tasks.append(task)
                            scheduled_this_shift.add(best_station)
                            station_states[best_station] = step.activity_id
                            
                            # Update completed units (persists across days)
                            if step.step_id not in completed_units:
                                completed_units[step.step_id] = set()
                            completed_units[step.step_id].update(units)
                            
                            # Remove this work and check for more units
                            available_work.remove((step, po, units))
                            new_units = self._get_available_units(
                                step, po, completed_units, in_progress_units
                            )
                            if new_units:
                                available_work.append((step, po, new_units))
                            break

                # Print end of day progress if PM shift
                if time_slot == "PM":
                    print(f"\n  End of Day Progress:")
                    for po in purchase_orders:
                        po_steps = [s for s in steps if s.purchase_order_id == po.id]
                        progress, active_steps = self._calculate_po_progress(
                            po, po_steps, completed_units
                        )
                        print(f"    Order {po.id}: {progress:.1f}% complete "
                              f"({active_steps}/8 steps active)")

        return scheduled_tasks

    def _find_next_priority_steps(self,
                                purchase_orders: List[PurchaseOrder],
                                steps: List[ProductionStep],
                                completed_units: Dict[str, set],
                                used_stations: set) -> List[tuple[ProductionStep, PurchaseOrder]]:
        """Find next priority steps that could be started."""
        candidates = []
        
        for po in sorted(purchase_orders, key=lambda x: x.effective_priority, reverse=True):
            po_steps = [s for s in steps if s.purchase_order_id == po.id]
            
            for step in po_steps:
                # Skip if complete
                if step.step_id in completed_units and \
                   len(completed_units[step.step_id]) >= po.units:
                    continue
                    
                # Calculate priority score
                score = self._calculate_step_score(step, po, completed_units)
                candidates.append((score, step, po))
        
        # Sort by score and return step-po pairs
        return [(step, po) for _, step, po in sorted(candidates, reverse=True)]
    
    def _create_simple_schedule(self, purchase_orders: List[PurchaseOrder], steps: List[ProductionStep]) -> List[ScheduledTask]:
        scheduled_tasks = []
        
        # Pre-calculate total tasks needed
        total_needed = len(self.date_list) * 24  # 10 days × 24 tasks per day
        
        # Create schedule day by day
        for day in self.date_list:
            for time_slot in ["AM", "PM"]:
                # Must schedule exactly 12 tasks this shift
                stations_used = set()
                
                # Track units completed per step
                units_completed = {}  # step_id -> set(unit numbers)
                
                # Group steps by activity and PO
                activity_po_steps = {}  # (activity_id, po_id) -> List[steps]
                for step in steps:
                    key = (step.activity_id, step.purchase_order_id)
                    if key not in activity_po_steps:
                        activity_po_steps[key] = []
                    activity_po_steps[key].append(step)
                
                # Sort by PO priority
                po_priority = {po.id: po.effective_priority for po in purchase_orders}
                po_units = {po.id: po.units for po in purchase_orders}
                
                # Schedule steps on available stations
                while len(stations_used) < 12:  # Changed comparison to check set size
                    # Find steps ready to schedule
                    ready_steps = []
                    for (activity, po_id), step_list in activity_po_steps.items():
                        for step in step_list:
                            # Check if all units are complete
                            if step.step_id not in units_completed:
                                units_completed[step.step_id] = set()
                            
                            if len(units_completed[step.step_id]) >= po_units[step.purchase_order_id]:
                                continue
                            
                            # Check dependencies
                            can_start = True
                            for dep_id in step.depends_on:
                                if dep_id not in units_completed or \
                                   len(units_completed[dep_id]) < step.min_units_to_start:
                                    can_start = False
                                    break
                            
                            if can_start:
                                ready_steps.append(step)
                    
                    if not ready_steps:
                        # Fill remaining stations with IDLE tasks
                        remaining_stations = set(range(1, 13)) - stations_used
                        for station_num in remaining_stations:
                            scheduled_tasks.append(
                                ScheduledTask(
                                    step_id="IDLE",
                                    station_id=f"S{station_num}",
                                    day=day,
                                    time_slot=time_slot,
                                    purchase_order_id="NONE",
                                    activity_id="IDLE",
                                    units_start=0,
                                    units_end=0
                                )
                            )
                            stations_used.add(station_num)
                        break
                    
                    # Sort ready steps by priority
                    ready_steps.sort(key=lambda s: po_priority[s.purchase_order_id], reverse=True)
                    
                    # Schedule highest priority step
                    step = ready_steps[0]
                    station_num = min(set(range(1, 13)) - stations_used)
                    stations_used.add(station_num)
                    
                    # Calculate units to process
                    if step.step_id not in units_completed:
                        units_completed[step.step_id] = set()
                    
                    remaining_units = po_units[step.purchase_order_id] - len(units_completed[step.step_id])
                    units_this_slot = min(remaining_units, step.units_per_station)
                    
                    start_unit = max(units_completed[step.step_id]) + 1 if units_completed[step.step_id] else 1
                    end_unit = start_unit + units_this_slot - 1
                    
                    scheduled_tasks.append(
                        ScheduledTask(
                            step_id=step.step_id,
                            station_id=f"S{station_num}",
                            day=day,
                            time_slot=time_slot,
                            purchase_order_id=step.purchase_order_id,
                            activity_id=step.activity_id,
                            units_start=start_unit,
                            units_end=end_unit
                        )
                    )
                    
                    # Update completed units
                    units_completed[step.step_id].update(range(start_unit, end_unit + 1))
        
        # Verify we have exactly the right number of tasks
        assert len(scheduled_tasks) == total_needed, \
            f"Schedule incomplete: {len(scheduled_tasks)} tasks vs {total_needed} needed"
        
        return scheduled_tasks
    
    def _format_stations(self, stations: List[Station]) -> str:
        """Format station list showing current activities."""
        return "\n".join([
            f"- Station {station.id} "
            f"(Current Activity: {station.current_activity_id or 'None'})"
            for station in stations
        ])
    
    def _format_pos(self, purchase_orders: List[PurchaseOrder]) -> str:
        return "\n".join([
            f"- PO {po.id}: Priority={po.effective_priority}, Due={po.due_date}"
            for po in purchase_orders
        ])
    
    def _format_steps(self, steps: List[ProductionStep]) -> str:
        return "\n".join([
            f"- Step {step.step_id}: PO={step.purchase_order_id}, "
            f"Activity={step.activity_id}, Dependencies={step.depends_on}"
            for step in steps
        ])

    def _format_locked_assignments(self, assignments: Set[LockedAssignment]) -> str:
        return "\n".join([
            f"- {assignment.step_id} at {assignment.day} ({assignment.time_slot}) "
            f"on station {assignment.station_id}"
            for assignment in assignments
        ])

    def _format_violation_history(self, violations: List[Dict]) -> str:
        """Format violation history for agent prompts."""
        if not violations:
            return "No previous violations."
            
        formatted = []
        for record in violations:  # Each record is from one iteration
            iteration = record['iteration']
            for v in record['violations']:  # Get the actual violations from the record
                if v['type'] == 'dependency_violation':
                    formatted.append(
                        f"Iteration {iteration}: Dependency issue - Step {v['step_id']} "
                        f"must wait for {v['related_step_id']}"
                    )
                elif v['type'] == 'employee_unavailable':
                    formatted.append(
                        f"Iteration {iteration}: Availability issue - Employee {v['employee_id']} "
                        f"unavailable on {v['day']}"
                    )
                elif v['type'] == 'station_conflict':
                    formatted.append(
                        f"Iteration {iteration}: Station conflict - {v['station_id']} "
                        f"overbooked on {v['day']}"
                    )
        
        return "\n".join(formatted)

    def _format_steps_with_times(self, steps: List[ProductionStep]) -> str:
        return "\n".join([
            f"- Step {step.step_id}: PO={step.purchase_order_id}, "
            f"Activity={step.activity_id}, Dependencies={step.depends_on}, "
            f"Setup={step.setup_time_days}d, Duration={step.duration_days}d, "
            f"Teardown={step.teardown_time_days}d"
            for step in steps
        ])

    def _calculate_utilization(self, tasks: List[ScheduledTask]) -> str:
        """Calculate detailed utilization metrics."""
        if not tasks:
            return "0% (No tasks scheduled)"
            
        total_slots = 12 * 2 * len(self.date_list)  # stations * shifts * days
        used_slots = len(tasks)
        
        # Calculate shift-specific metrics
        am_slots = len([t for t in tasks if t.time_slot == "AM"])
        pm_slots = len([t for t in tasks if t.time_slot == "PM"])
        
        # Calculate station utilization
        station_usage = {}
        for task in tasks:
            if task.station_id not in station_usage:
                station_usage[task.station_id] = 0
            station_usage[task.station_id] += 1
        
        avg_station_util = sum(station_usage.values()) / (len(station_usage) * 20) * 100 if station_usage else 0
        
        return f"""
        Overall: {(used_slots / total_slots) * 100:.1f}%
        AM Shift: {(am_slots / (total_slots/2)) * 100:.1f}%
        PM Shift: {(pm_slots / (total_slots/2)) * 100:.1f}%
        Avg Station: {avg_station_util:.1f}%
        """

    def _format_schedule_status(self, tasks: List[ScheduledTask]) -> str:
        """Format current schedule status with shift details."""
        if not tasks:
            return "No tasks scheduled yet."
            
        utilization = self._calculate_slot_utilization(tasks)
        status = [
            f"Current Utilization:",
            f"- AM Shift: {utilization['AM']:.1f}%",
            f"- PM Shift: {utilization['PM']:.1f}%",
            f"- Overall: {utilization['Total']:.1f}%",
            "\nScheduled Tasks by Shift:"
        ]
        
        # Group by day and shift
        by_day_shift = {}
        for task in sorted(tasks, key=lambda t: (t.day, t.time_slot)):
            key = (task.day, task.time_slot)
            if key not in by_day_shift:
                by_day_shift[key] = []
            by_day_shift[key].append(task)
            
        for (day, shift), shift_tasks in sorted(by_day_shift.items()):
            status.append(f"\n{day} - {shift}:")
            for task in shift_tasks:
                status.append(f"  - Task {task.step_id} on Station {task.station_id}")
                
        return "\n".join(status)

    def _analyze_dependency_chains(self, steps: List[ProductionStep]) -> Dict[str, List[str]]:
        """Analyze and group steps by dependency chains."""
        # Build dependency graph
        dep_graph = {}
        for step in steps:
            dep_graph[step.step_id] = {
                'deps': step.depends_on,
                'station': step.station_id,
                'po': step.purchase_order_id
            }
        
        # Find root steps (no dependencies)
        roots = [step.step_id for step in steps if not step.depends_on]
        
        # Track chains
        chains = {}
        for root in roots:
            chain = [root]
            current = root
            while True:
                # Find steps that depend on current
                next_steps = [
                    s.step_id for s in steps 
                    if current in s.depends_on
                ]
                if not next_steps:
                    break
                current = next_steps[0]  # Take first dependent step
                chain.append(current)
            chains[root] = chain
        
        return chains 

    def _format_station_activities(self) -> str:
        """Format current station activity assignments."""
        return "\n".join([
            f"- Station {s.id}: Currently set up for "
            f"{s.current_activity_id or 'any activity'}"
            for s in self.station_list
        ])

    def _track_station_states(self, schedule_data: Dict) -> Dict[str, Dict]:
        """Track station states (current activity and setup/teardown status) over time."""
        station_states = {}  # station_id -> {day -> {time_slot -> {activity, status}}}
        
        # Sort tasks chronologically
        tasks = sorted(
            schedule_data["tasks"], 
            key=lambda t: (t["day"], t["time_slot"] == "PM")
        )
        
        # Create lookup for activities
        activity_lookup = {
            (act["station_id"], act["day"], act["time_slot"]): act["activity_id"]
            for act in schedule_data.get("station_activities", [])
        }
        
        for task in tasks:
            station_id = task["station_id"]
            day = task["day"]
            time_slot = task["time_slot"]
            
            # Find corresponding activity
            activity = activity_lookup.get(
                (station_id, day, time_slot),
                # If no activity specified, try to find it from the step
                next((s.activity_id for s in self.production_steps if s.step_id == task["step_id"]), "Unknown")
            )
            
            # Initialize station tracking if needed
            if station_id not in station_states:
                station_states[station_id] = {}
            if day not in station_states[station_id]:
                station_states[station_id][day] = {}
            
            # Track this time slot's state
            station_states[station_id][day][time_slot] = {
                "activity": activity,
                "status": "active"  # Could be: setup, active, teardown
            }
            
        return station_states 

    def _calculate_time_diff(self, day1: str, slot1: str, day2: str, slot2: str) -> float:
        """Calculate time difference in days between two time slots."""
        date1 = datetime.date.fromisoformat(day1)
        date2 = datetime.date.fromisoformat(day2)
        days = (date2 - date1).days
        
        if slot1 == slot2:
            return days
        elif slot2 == "PM":  # slot1 is AM
            return days + 0.5
        else:  # slot1 is PM, slot2 is AM
            return days - 0.5

    def _validate_schedule_completeness(self, tasks: List[ScheduledTask]) -> bool:
        """Verify schedule covers all required slots."""
        if len(tasks) != 240:
            return False
            
        # Check each day has exactly 24 tasks
        tasks_per_day = {}
        for task in tasks:
            day = task.day
            if day not in tasks_per_day:
                tasks_per_day[day] = {"AM": set(), "PM": set()}
            tasks_per_day[day][task.time_slot].add(task.station_id)
        
        # Verify each shift has exactly 12 stations
        for day_tasks in tasks_per_day.values():
            if len(day_tasks["AM"]) != 12 or len(day_tasks["PM"]) != 12:
                return False
        
        return True

    def _format_processing_rates(self, steps: List[ProductionStep]) -> str:
        """Format processing rates and unit requirements for each step."""
        rates = []
        for step in steps:
            rates.append(
                f"Step {step.step_id}: "
                f"{step.units_per_station} units/station/slot, "
                f"needs {step.min_units_to_start} units complete to start"
            )
        return "\n".join(rates)

    def _calculate_step_score(self, step: ProductionStep, po: PurchaseOrder, 
                            completed_units: Dict[str, set]) -> float:
        """Calculate comprehensive score for scheduling a step."""
        
        # Base priority (0-40)
        priority_score = po.effective_priority * 0.4
        
        # Completion progress (0-20)
        units_done = len(completed_units.get(step.step_id, set()))
        progress = units_done / po.units
        progress_score = 20 * (1 - progress)  # More points for less complete steps
        
        # Dependency readiness (0-20)
        dep_score = 20
        for dep_id in step.depends_on:
            dep_units = len(completed_units.get(dep_id, set()))
            if dep_units < step.min_units_to_start:
                dep_score = 0
                break
        
        # Processing efficiency (0-20)
        efficiency = step.units_per_station / step.duration_days
        efficiency_score = min(20, efficiency * 10)
        
        return priority_score + progress_score + dep_score + efficiency_score

    def _get_dependency_chain(self, step: ProductionStep) -> List[str]:
        """Get all steps in this step's dependency chain."""
        chain = [step.step_id]
        for dep_id in step.depends_on:
            dep_step = next(s for s in self.production_steps if s.step_id == dep_id)
            chain.extend(self._get_dependency_chain(dep_step))
        return chain

    def _fill_remaining_stations(self,
                               remaining_count: int,
                               current_day: datetime.date,
                               time_slot: str,
                               next_steps: List[tuple[ProductionStep, PurchaseOrder]],
                               completed_units: Dict[str, set],
                               station_states: Dict[str, str],
                               scheduled_this_shift: set) -> List[ScheduledTask]:
        """Fill remaining stations with next priority work."""
        tasks = []
        
        for step, po in next_steps[:remaining_count]:
            # Find available station
            available_station = None
            for station in self.station_list:
                if station.id not in scheduled_this_shift:
                    available_station = station.id
                    break
                    
            if available_station:
                # Calculate units to process
                units_done = len(completed_units.get(step.step_id, set()))
                units_remaining = po.units - units_done
                units_this_slot = min(units_remaining, step.units_per_station)
                
                start_unit = units_done
                end_unit = start_unit + units_this_slot - 1
                
                task = ScheduledTask(
                    step_id=step.step_id,
                    purchase_order_id=po.id,
                    station_id=available_station,
                    activity_id=step.activity_id,
                    day=current_day,
                    time_slot=time_slot,
                    units_start=start_unit,
                    units_end=end_unit
                )
                
                tasks.append(task)
                scheduled_this_shift.add(available_station)
                station_states[available_station] = step.activity_id
                
                # Update completed units
                if step.step_id not in completed_units:
                    completed_units[step.step_id] = set()
                completed_units[step.step_id].update(range(start_unit, end_unit + 1))
        
        return tasks

    def _is_step_complete(self, step: ProductionStep, po: PurchaseOrder, 
                         completed_units: Dict[str, set]) -> bool:
        """Check if a step has completed all its units."""
        if step.step_id not in completed_units:
            return False
        return len(completed_units[step.step_id]) >= po.units

    def _get_step_progress(self, step: ProductionStep, po: PurchaseOrder,
                          completed_units: Dict[str, set]) -> float:
        """Get completion percentage for a step."""
        if step.step_id not in completed_units:
            return 0.0
        return len(completed_units[step.step_id]) / po.units * 100

    def _find_best_station(self, step: ProductionStep, 
                          station_states: Dict[str, str],
                          scheduled_this_shift: set) -> tuple[str, bool]:
        """Find best station for a step, considering current setup."""
        
        # First try stations already set up for this activity
        for station in self.station_list:
            if (station.id not in scheduled_this_shift and
                station_states[station.id] == step.activity_id):
                return station.id, False  # No setup needed
        
        # Then try stations with no activity
        for station in self.station_list:
            if (station.id not in scheduled_this_shift and
                not station_states[station.id]):
                return station.id, True  # Setup needed
        
        # Finally, try any available station
        for station in self.station_list:
            if station.id not in scheduled_this_shift:
                return station.id, True  # Setup needed
        
        return None, True

    def _get_dependent_steps(self, step_id: str, steps: List[ProductionStep]) -> List[str]:
        """Get all steps that depend on this one."""
        dependent_steps = []
        for step in steps:
            if step_id in step.depends_on:
                dependent_steps.append(step.step_id)
                # Also get steps that depend on this dependent step
                dependent_steps.extend(self._get_dependent_steps(step.step_id, steps))
        return list(set(dependent_steps))  # Remove duplicates

    def _can_start_step(self, step: ProductionStep, completed_units: Dict[str, set]) -> bool:
        """Check if a step can be started based on dependencies."""
        for dep_id in step.depends_on:
            dep_units = len(completed_units.get(dep_id, set()))
            if dep_units < step.min_units_to_start:
                return False
        return True

    def _get_available_units(self, step: ProductionStep, po: PurchaseOrder,
                           completed_units: Dict[str, set],
                           in_progress_units: Dict[str, set]) -> range:
        """Get range of units available to process."""
        # Units already completed
        done_units = completed_units.get(step.step_id, set())
        # Units currently being processed
        wip_units = in_progress_units.get(step.step_id, set())
        # All unavailable units
        unavailable = done_units | wip_units
        
        # Find first available unit
        start_unit = 0
        while start_unit < po.units:
            if start_unit not in unavailable:
                break
            start_unit += 1
            
        # Calculate how many units we can process
        end_unit = min(
            start_unit + step.units_per_station - 1,  # Station capacity
            po.units - 1  # Don't exceed total units needed
        )
        
        if start_unit <= end_unit:  # Only return range if valid
            return range(start_unit, end_unit + 1)
        return range(0)  # Empty range if no units available

    def _calculate_po_progress(self, po: PurchaseOrder, po_steps: List[ProductionStep], 
                             completed_units: Dict[str, set]) -> tuple[float, int]:
        """Calculate cumulative PO progress as percentage and count of active steps."""
        total_units_needed = po.units * len(po_steps)  # Total units needed across all steps
        total_units_completed = 0  # Total units completed across all steps
        active_steps = 0
        
        for step in po_steps:
            units_complete = len(completed_units.get(step.step_id, set()))
            total_units_completed += units_complete
            if units_complete > 0:
                active_steps += 1
        
        # Overall progress is total completed units / total needed units
        progress = (total_units_completed / total_units_needed) * 100
        return progress, active_steps