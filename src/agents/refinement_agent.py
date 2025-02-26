from typing import List, Callable, Set, Dict
import json
import datetime
from crewai import Task, Crew
from .base_agent import BaseAgent
from ..models.scheduled_task import ScheduledTask
from ..models.production_step import ProductionStep
from ..models.employee import Employee
from ..models.purchase_order import PurchaseOrder
from .constraints_agent import ConstraintsAgent
from ..models.locked_assignment import LockedAssignment
from ..config import STATIONS_PER_DAY, WORKERS_PER_STATION, MAX_WORKER_TASKS_PER_DAY
import copy

class RefinementAgent(BaseAgent):
    """
    Agent responsible for improving schedule quality through local modifications.
    """
    
    def __init__(self):
        super().__init__(
            name="Schedule Optimizer",
            role="Schedule Optimization Specialist",
            goal="Maximize production progress while maintaining feasibility",
            backstory="""
            Expert in optimizing production schedules to maximize throughput.
            Focuses on completing as many high-priority tasks as possible
            while respecting all constraints. Prefers solutions that:
            1. Complete more steps of high-priority orders
            2. Utilize available resources efficiently
            3. Minimize idle time between dependent steps
            4. Keep critical paths moving
            """
        )
    
    def refine_schedule(self,
                       scheduled_tasks: List[ScheduledTask],
                       scoring_func,
                       constraints_agent,
                       steps: List[ProductionStep],
                       employees: List[Employee],
                       purchase_orders: List[PurchaseOrder],
                       locked_assignments: Set[LockedAssignment] = None,
                       previous_reasoning: Dict[str, str] = None,
                       previous_violations: List[Dict] = None) -> List[ScheduledTask]:
        """Refine schedule to improve score while maintaining feasibility."""
        
        previous_reasoning = previous_reasoning or {}
        previous_violations = previous_violations or []
        
        current_score = scoring_func(scheduled_tasks)
        
        task = Task(
            description=f"""
            Previous Agents' Reasoning:
            Priority Agent: {previous_reasoning.get('priority', 'No reasoning')}
            Sequence Agent: {previous_reasoning.get('sequence', 'No reasoning')}
            Resource Agent: {previous_reasoning.get('resource', 'No reasoning')}

            Previous Violations to Avoid:
            {self._format_violation_history(previous_violations)}

            Analyze and improve the current production schedule to maximize progress:

            Current Schedule:
            {self._format_current_schedule(scheduled_tasks)}

            Production Steps Info:
            {self._format_steps(steps)}

            Employee Availability:
            {self._format_employees(employees)}

            Current Schedule Score: {current_score}

            Schedule Capacity:
            - Total available slots: 240 (12 stations * 2 shifts * 10 days)
            - Current utilization: {len(scheduled_tasks)} slots used
            - Each task needs either AM or PM slot
            - Tasks can be split across shifts if needed

            Scheduling Constraints:
            1. Maximum {STATIONS_PER_DAY} parallel stations per shift
            2. Each station has AM and PM shifts
            3. Workers can work different stations in AM vs PM
            4. Setup/teardown times must be respected between shifts
            5. Dependencies and worker skills must be maintained

            CRITICAL SCHEDULING REQUIREMENTS:
            1. MAXIMIZE STATION USAGE:
               - Every station MUST run both AM and PM shifts
               - Only skip a shift if absolutely necessary due to constraints
               - Current utilization of {len(scheduled_tasks)/240*100:.1f}% is unacceptable
            
            2. OPTIMIZE DAILY WORKLOAD:
               - Target: 24 tasks per day (12 stations × 2 shifts)
               - Current average: {len(scheduled_tasks)/10:.1f} tasks per day
               - Fill all available slots unless blocked by constraints
            
            3. BALANCE SHIFTS:
               - AM and PM shifts should have equal utilization
               - Move tasks between shifts to achieve balance
               - Keep dependencies and setup times valid
            
            CRITICAL OPTIMIZATION GOALS:
            1. MAXIMIZE PARALLEL PROCESSING:
               - Every shift must use all 12 stations
               - Current utilization: {self._calculate_utilization(scheduled_tasks)}
               - Find opportunities to run more steps in parallel
            2. MAINTAIN EFFICIENCY:
               - Group similar activities to minimize changeovers
               - Keep setup/teardown times between shifts
            3. PRESERVE FEASIBILITY:
               - Respect all dependencies and constraints
               - Maintain employee skill requirements
            
            Focus first on filling any under-utilized shifts to reach 12 stations.

            Unit Processing Analysis:
            {self._analyze_unit_progress(scheduled_tasks, steps, purchase_orders)}

            Parallel Processing Opportunities:
            {self._analyze_parallel_opportunities(scheduled_tasks, steps, purchase_orders)}

            OPTIMIZATION PRIORITIES:
            1. MAXIMIZE PARALLEL UNIT PROCESSING:
               - Each step can handle {self._format_step_capacities(steps)}
               - Current parallel utilization: {self._calculate_parallel_utilization(scheduled_tasks)}
               - Find opportunities to process more units simultaneously
            
            2. OPTIMIZE UNIT FLOW:
               - Minimize waiting time between dependent steps
               - Start next steps as soon as minimum units complete
               - Keep units moving through production pipeline
            
            3. BALANCE STATION LOADING:
               - Use all 12 stations each shift
               - Distribute units across available stations
               - Consider setup/teardown when changing activities
            """,
            expected_output="""
            Respond with a JSON object containing proposed changes:
            {
                "modifications": [
                    {
                        "task_id": "ST-1",
                        "changes": {
                            "employee_id": "E2",
                            "day": "2024-03-15"
                        }
                    }
                ],
                "expected_benefits": "Detailed explanation of how these changes improve throughput"
            }
            IMPORTANT: Ensure the response is ONLY the JSON array, with no additional text.
            """,
            agent=self.agent
        )
        
        crew = Crew(
            agents=[self.agent],
            tasks=[task],
            verbose=True
        )
        
        result = crew.kickoff()
        try:
            # Clean the result string to ensure it's valid JSON
            result_str = str(result).strip()
            if result_str.startswith('```json'):
                result_str = result_str.split('```json')[1]
            if result_str.endswith('```'):
                result_str = result_str.split('```')[0]
            result_str = result_str.strip()
            
            improvements = json.loads(result_str)
            
            # Create a copy of the schedule to test modifications
            test_schedule = [ScheduledTask(**vars(t)) for t in scheduled_tasks]
            
            # Apply proposed changes
            for mod in improvements.get("modifications", []):
                task_id = mod["task_id"]
                change = mod["changes"]
                
                for task in test_schedule:
                    if task.step_id == task_id:
                        if "employee_id" in change:
                            task.employee_id = change["employee_id"]
                        if "day" in change:
                            # Extract just the date part before "Date: " prefix
                            date_str = change["day"].replace("Date: ", "")
                            task.day = datetime.date.fromisoformat(date_str)
                        if "time_slot" in change:
                            # Extract just the shift part after "Shift: " prefix
                            shift = change["time_slot"].replace("Shift: ", "")
                            task.time_slot = shift
                        if "station_id" in change:
                            task.station_id = change["station_id"]
            
            # Verify the modified schedule is feasible
            if constraints_agent.check_feasibility(test_schedule, steps, employees, previous_reasoning)[0]:  # Get first element of tuple
                new_score = scoring_func(test_schedule)
                if new_score > current_score:
                    print(f"Schedule improved: {improvements['expected_benefits']}")
                    return test_schedule
            
            print("Proposed improvements did not yield a better feasible schedule")
            return scheduled_tasks
            
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"Warning: Could not parse refinement suggestions ({str(e)})")
            return scheduled_tasks
    
    def _format_current_schedule(self, tasks: List[ScheduledTask]) -> str:
        # Group by day and shift
        schedule_slots = {}  # (day, time_slot) -> List[tasks]
        for task in sorted(tasks, key=lambda t: (t.day, t.time_slot)):
            key = (task.day, task.time_slot)
            if key not in schedule_slots:
                schedule_slots[key] = []
            schedule_slots[key].append(task)
            
        formatted = []
        for (day, slot), slot_tasks in schedule_slots.items():
            formatted.append(f"\n{day} - {slot} Shift:")
            for task in slot_tasks:
                formatted.append(
                    f"  - Task {task.step_id}: Station={task.station_id}, "
                    f"Employee={task.employee_id}"
                )
        return "\n".join(formatted)
    
    def _format_steps(self, steps: List[ProductionStep]) -> str:
        return "\n".join([
            f"- Step {step.step_id}: Activity={step.activity_id}, "
            f"Duration={step.duration_days} days, Dependencies={step.depends_on}"
            for step in steps
        ])
    
    def _format_employees(self, employees: List[Employee]) -> str:
        return "\n".join([
            f"- {emp.name} (ID={emp.id}): Skills={emp.skills}, "
            f"Available={emp.availability}"
            for emp in employees
        ])

    def _format_current_activities(self, tasks: List[ScheduledTask], steps: List[ProductionStep]) -> str:
        """Format current station activities."""
        station_activities = {}  # (station_id, day, time_slot) -> activity_id
        for task in sorted(tasks, key=lambda t: (t.day, t.time_slot)):
            step = next((s for s in steps if s.step_id == task.step_id), None)
            if step:
                station_activities[(task.station_id, task.day, task.time_slot)] = step.activity_id
        
        return "\n".join(
            f"Station {station_id} on {day} {time_slot}: Activity {activity_id}"
            for (station_id, day, time_slot), activity_id 
            in sorted(station_activities.items())
        )

    def _analyze_schedule_efficiency(self, tasks: List[ScheduledTask], steps: List[ProductionStep]) -> str:
        """Analyze schedule efficiency including activity changes."""
        activity_changes = {}  # station_id -> count of activity changes
        current_activities = {}  # station_id -> (activity_id, day, time_slot)
        
        for task in sorted(tasks, key=lambda t: (t.day, t.time_slot)):
            if task.station_id not in current_activities:
                current_activities[task.station_id] = (task.activity_id, task.day, task.time_slot)
                activity_changes[task.station_id] = 0
            else:
                prev_activity, prev_day, prev_slot = current_activities[task.station_id]
                if prev_activity != task.activity_id:
                    activity_changes[task.station_id] += 1
                current_activities[task.station_id] = (task.activity_id, task.day, task.time_slot)
        
        return f"""
        Activity Change Analysis:
        - Total activity changes: {sum(activity_changes.values())}
        - Average changes per station: {sum(activity_changes.values())/len(activity_changes) if activity_changes else 0:.1f}
        - Most changes on a single station: {max(activity_changes.values()) if activity_changes else 0}
        - Stations with no changes: {sum(1 for c in activity_changes.values() if c == 0)}
        """

    def _calculate_utilization(self, tasks: List[ScheduledTask]) -> str:
        shift_usage = {}  # (day, time_slot) -> count
        for task in tasks:
            key = (task.day, task.time_slot)
            if key not in shift_usage:
                shift_usage[key] = 0
            shift_usage[key] += 1
        
        total_shifts = len(set((t.day, t.time_slot) for t in tasks))
        if not total_shifts:
            return "0%"
            
        avg_utilization = sum(shift_usage.values()) / (total_shifts * 12) * 100
        under_utilized = sum(1 for count in shift_usage.values() if count < 12)
        
        return f"{avg_utilization:.1f}% (with {under_utilized} under-utilized shifts)"

    def _analyze_unit_progress(self, tasks: List[ScheduledTask], steps: List[ProductionStep], pos: List[PurchaseOrder]) -> str:
        # Track units completed per step
        progress = {}  # (po_id, step_id) -> completed_units
        for task in sorted(tasks, key=lambda t: (t.day, t.time_slot == "PM")):
            key = (task.purchase_order_id, task.step_id)
            if key not in progress:
                progress[key] = set()
            progress[key].update(range(task.units_start, task.units_end + 1))
        
        # Format progress report
        report = []
        for po in pos:
            po_steps = [s for s in steps if s.purchase_order_id == po.id]
            report.append(f"\nPO {po.id} ({po.units} units):")
            for step in sorted(po_steps, key=lambda s: s.step_order):
                completed = len(progress.get((po.id, step.step_id), set()))
                report.append(
                    f"- Step {step.step_id}: {completed}/{po.units} units complete "
                    f"({completed/po.units*100:.1f}%)"
                )
        return "\n".join(report)

    def _analyze_parallel_opportunities(self, tasks: List[ScheduledTask], steps: List[ProductionStep], pos: List[PurchaseOrder]) -> str:
        opportunities = []
        
        # Group tasks by day/shift
        shift_tasks = {}  # (day, time_slot) -> List[tasks]
        for task in tasks:
            key = (task.day, task.time_slot)
            if key not in shift_tasks:
                shift_tasks[key] = []
            shift_tasks[key].append(task)
        
        # Analyze each shift
        for (day, slot), shift_tasks in sorted(shift_tasks.items()):
            used_stations = len(shift_tasks)
            if used_stations < 12:
                # Find steps that could run in parallel
                ready_steps = []
                for po in pos:
                    po_steps = [s for s in steps if s.purchase_order_id == po.id]
                    for step in po_steps:
                        # Check if step has units ready to process
                        completed_deps = self._count_completed_units(step, tasks, day, slot)
                        if completed_deps >= step.min_units_to_start:
                            ready_steps.append((step, completed_deps))
                
                if ready_steps:
                    opportunities.append(
                        f"\n{day} {slot}:"
                        f"- {12 - used_stations} stations available"
                        f"- Could process: " + ", ".join(
                            f"Step {s.step_id} ({u} units ready)"
                            for s, u in ready_steps[:3]  # Show top 3
                        )
                    )
        
        return "\n".join(opportunities)

    def _count_completed_units(self, step: ProductionStep, tasks: List[ScheduledTask], 
                             up_to_day: datetime.date, up_to_slot: str) -> int:
        completed_units = set()
        for dep_id in step.depends_on:
            dep_tasks = [
                t for t in tasks 
                if t.step_id == dep_id and (
                    t.day < up_to_day or 
                    (t.day == up_to_day and t.time_slot < up_to_slot)
                )
            ]
            for task in dep_tasks:
                completed_units.update(range(task.units_start, task.units_end + 1))
        return len(completed_units)

    def _format_step_capacities(self, steps: List[ProductionStep]) -> str:
        capacities = {}  # activity_id -> List[units_per_station]
        for step in steps:
            if step.activity_id not in capacities:
                capacities[step.activity_id] = []
            capacities[step.activity_id].append(step.units_per_station)
        
        return "\n".join(
            f"Activity {act}: {min(caps)}-{max(caps)} units/station/slot"
            for act, caps in sorted(capacities.items())
        )

    def _calculate_parallel_utilization(self, tasks: List[ScheduledTask]) -> str:
        shift_stats = {}  # (day, slot) -> (stations_used, total_units)
        for task in tasks:
            key = (task.day, task.time_slot)
            if key not in shift_stats:
                shift_stats[key] = [0, 0]
            shift_stats[key][0] += 1
            shift_stats[key][1] += task.units_end - task.units_start + 1
        
        if not shift_stats:
            return "No tasks scheduled"
            
        avg_stations = sum(s[0] for s in shift_stats.values()) / len(shift_stats)
        avg_units = sum(s[1] for s in shift_stats.values()) / len(shift_stats)
        return f"{avg_stations:.1f} stations/shift, {avg_units:.1f} units/shift"

    def _suggest_task_changes(self, 
                            task: ScheduledTask,
                            steps: List[ProductionStep],
                            employees: List[Employee],
                            violations: List[Dict]) -> Dict:
        """Suggest changes to resolve violations."""
        changes = {}
        
        # Example: If suggesting a new day/slot
        if some_condition:
            # Keep date and time_slot separate
            changes["day"] = "2025-02-19"  # Just the date
            changes["time_slot"] = "PM"    # Separate time slot
        
        return changes 

    def _format_sequence_plan(self, tasks: List[ScheduledTask], purchase_orders: List[PurchaseOrder]) -> str:
        """Format sequence plan for our 3 orders (PO-101, PO-102, PO-103)."""
        plan = ["### Production Sequence Plan\n"]
        
        # Group by priority level
        priority_groups = {
            "Critical": [],     # 80-100
            "High": [],        # 60-79 
            "Standard": []     # 0-59
        }
        
        for po in purchase_orders:
            if po.effective_priority >= 80:
                priority_groups["Critical"].append(po)
            elif po.effective_priority >= 60:
                priority_groups["High"].append(po)
            else:
                priority_groups["Standard"].append(po)
        
        # Format each priority group
        for priority, orders in priority_groups.items():
            if orders:
                plan.append(f"\n**{priority} Priority Orders:**")
                for po in sorted(orders, key=lambda x: x.effective_priority, reverse=True):
                    days_to_due = (po.due_date - datetime.date.today()).days
                    po_tasks = [t for t in tasks if t.purchase_order_id == po.id]
                    completed_units = len(set(t.units_start for t in po_tasks))
                    
                    plan.append(f"- Order {po.id}:")
                    plan.append(f"  • Due in {days_to_due} days")
                    plan.append(f"  • {completed_units}/{po.units} units started")
                    plan.append(f"  • Priority Score: {po.effective_priority}")
                    plan.append(f"  • Value: ${po.value:,}") 