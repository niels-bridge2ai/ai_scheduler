from typing import List, Dict, Set
from crewai import Crew, Task
from .models.locked_assignment import LockedAssignment
from .models.purchase_order import PurchaseOrder
from .models.production_step import ProductionStep
from .models.employee import Employee
from .models.scheduled_task import ScheduledTask
from .agents.priority_agent import PriorityAgent
from .agents.step_sequencer import StepSequencer
from .agents.resource_assigner import ResourceAssigner
from .agents.constraints_agent import ConstraintsAgent
from .agents.refinement_agent import RefinementAgent
import json

class SchedulingOrchestrator:
    """
    Coordinates the scheduling process using a progressive scheduling approach.
    """
    
    def __init__(self,
                 priority_agent: PriorityAgent,
                 step_sequencer: StepSequencer,
                 resource_assigner: ResourceAssigner,
                 constraints_agent: ConstraintsAgent,
                 refinement_agent: RefinementAgent):
        self.priority_agent = priority_agent
        self.step_sequencer = step_sequencer
        self.resource_assigner = resource_assigner
        self.constraints_agent = constraints_agent
        self.refinement_agent = refinement_agent
        self.locked_assignments: Set[LockedAssignment] = set()
        self.constraint_history: List[Dict] = []  # Track violations
        self.production_steps = None  # Will be set during run_scheduling_loop
        
        self.crew = Crew(
            agents=[
                priority_agent.agent,
                step_sequencer.agent,
                resource_assigner.agent,
                constraints_agent.agent,
                refinement_agent.agent
            ],
            tasks=[],
            verbose=True
        )
    
    def run_scheduling_loop(self, 
                          purchase_orders: List[PurchaseOrder],
                          production_steps: List[ProductionStep],
                          employees: List[Employee],
                          max_iterations: int = 3) -> tuple[List[ScheduledTask], bool]:
        """Run multiple iterations to improve schedule quality."""
        self.production_steps = production_steps  # Store for scoring
        best_schedule = []
        best_score = 0.0
        found_feasible = False
        
        sorted_steps = self._sort_steps_by_priority(production_steps, purchase_orders)
        steps_to_schedule = sorted_steps.copy()
        
        for iteration in range(max_iterations):
            print(f"\n--- Iteration {iteration+1} ---")
            
            # Step 1: Priority Analysis
            print("\n=== Priority Analysis ===")
            priority_crew = Crew(
                agents=[self.priority_agent.agent],
                tasks=[Task(
                    description="Analyze and update purchase order priorities...",
                    expected_output="Priority analysis and reasoning",
                    agent=self.priority_agent.agent
                )],
                verbose=True
            )
            priority_result = str(priority_crew.kickoff())
            print("\nPriority Agent Output:")
            print(json.dumps(priority_result, indent=2))
            
            # Update priorities and pass reasoning to next agent
            self.priority_agent.update_priorities(
                purchase_orders=purchase_orders,
                steps=production_steps,
                previous_reasoning=priority_result,
                previous_violations=self.constraint_history
            )
            
            print("\nUpdated Priorities:")
            for po in purchase_orders:
                print(f"PO {po.id}: {po.effective_priority}")
            
            # Step 2: Sequence Planning
            print("\n=== Initial Scheduling ===")
            sequence_crew = Crew(
                agents=[self.step_sequencer.agent],
                tasks=[Task(
                    description=f"""
                    Create schedule based on priority agent's reasoning:
                    {priority_result}
                    
                    Previous violations to avoid:
                    {self._format_violation_history(self.constraint_history)}
                    """,
                    expected_output="Sequence plan and reasoning",
                    agent=self.step_sequencer.agent
                )],
                verbose=True
            )
            sequence_result = str(sequence_crew.kickoff())
            print("\nSequence Agent Output:")
            print(json.dumps(sequence_result, indent=2))
            
            # Create schedule and pass reasoning forward
            candidate_schedule = self.step_sequencer.create_schedule(
                purchase_orders=purchase_orders,
                steps=steps_to_schedule,
                locked_assignments=self.locked_assignments,
                previous_violations=self.constraint_history,
                previous_reasoning=sequence_result
            )
            
            print("\nInitial Schedule:")
            self._print_schedule(candidate_schedule)
            
            # Step 3: Resource Assignment
            print("\n=== Resource Assignment ===")
            resource_crew = Crew(
                agents=[self.resource_assigner.agent],
                tasks=[Task(
                    description=f"""
                    Assign resources based on sequence planner's reasoning:
                    {sequence_result}
                    """,
                    expected_output="Resource assignments and reasoning",
                    agent=self.resource_assigner.agent
                )],
                verbose=True
            )
            resource_result = str(resource_crew.kickoff())
            print("\nResource Agent Output:")
            print(json.dumps(resource_result, indent=2))
            
            # Assign resources with previous context
            self.resource_assigner.assign_resources(
                scheduled_tasks=candidate_schedule,
                production_steps=steps_to_schedule,
                locked_assignments=self.locked_assignments,
                previous_violations=self.constraint_history,
                previous_reasoning=resource_result
            )
            
            print("\nSchedule with Resources:")
            self._print_schedule(candidate_schedule)
            
            # Step 4: Constraint Checking
            print("\n=== Constraint Checking ===")
            is_feasible, violations = self.constraints_agent.check_feasibility(
                candidate_schedule, 
                steps_to_schedule, 
                employees,
                previous_reasoning=[priority_result, sequence_result, resource_result]
            )
            
            print(f"\nFeasible: {is_feasible}")
            if violations:
                print(f"Violations found: {len(violations)}")
                print("\nDetailed Violations:")
                for v in violations:
                    try:
                        if v['type'] == 'dependency_violation':
                            print(f"- Dependency: Step {v.get('step_id', 'unknown')} started before {v.get('related_step_id', 'unknown')} had enough units")
                        elif v['type'] == 'employee_unavailable':
                            print(f"- Worker {v.get('employee_id', 'unknown')} unavailable on {v.get('day', 'unknown')} {v.get('time_slot', 'unknown')}")
                        elif v['type'] == 'station_conflict':
                            print(f"- Station {v.get('station_id', 'unknown')} double-booked on {v.get('day', 'unknown')} {v.get('time_slot', 'unknown')}")
                        elif v['type'] == 'worker_overload':
                            print(f"- Worker {v.get('employee_id', 'unknown')} overloaded on {v.get('day', 'unknown')} {v.get('time_slot', 'unknown')}")
                        elif v['type'] == 'setup_teardown_violation':
                            print(f"- Setup/Teardown conflict on Station {v.get('station_id', 'unknown')} at {v.get('day', 'unknown')} {v.get('time_slot', 'unknown')}")
                        else:
                            print(f"- Other violation: {v}")
                    except Exception as e:
                        print(f"- Error printing violation: {v}")
                        print(f"  Error details: {str(e)}")
            
            if is_feasible:
                found_feasible = True
                refined_schedule = self.refinement_agent.refine_schedule(
                    scheduled_tasks=candidate_schedule,
                    scoring_func=self._score_schedule,
                    constraints_agent=self.constraints_agent,
                    steps=steps_to_schedule,
                    employees=employees,
                    purchase_orders=purchase_orders,
                    locked_assignments=self.locked_assignments,
                    previous_reasoning={
                        'priority': priority_result,
                        'sequence': sequence_result,
                        'resource': resource_result
                    },
                    previous_violations=self.constraint_history
                )
                
                print("\nRefined Schedule:")
                self._print_schedule(refined_schedule)
                
                score = self._score_schedule(refined_schedule)
                print(f"Schedule score: {score}")
                
                if score > best_score:
                    best_score = score
                    best_schedule = refined_schedule
                    
                # Lock successful assignments but don't return yet
                new_locks = self._identify_successful_assignments(
                    refined_schedule, steps_to_schedule
                )
                self.locked_assignments.update(new_locks)
            else:
                print("Schedule not feasible. Learning from violations...")
                self.constraint_history.append({
                    'iteration': iteration,
                    'violations': violations
                })
        
        # Return best schedule found across all iterations
        return (best_schedule if found_feasible else candidate_schedule), found_feasible
    
    def _sort_steps_by_priority(self, 
                              steps: List[ProductionStep],
                              purchase_orders: List[PurchaseOrder]) -> List[ProductionStep]:
        """Sort steps by PO priority and dependencies."""
        po_priority_map = {po.id: po.effective_priority for po in purchase_orders}
        
        # Create dependency graph
        dep_graph = {step.step_id: step.depends_on for step in steps}
        
        def get_step_priority(step: ProductionStep) -> float:
            base_priority = po_priority_map[step.purchase_order_id]
            dep_depth = len(self._get_all_dependencies(step.step_id, dep_graph))
            return base_priority + (dep_depth * 10)  # Prioritize steps with dependencies
        
        return sorted(steps, key=get_step_priority, reverse=True)
    
    def _get_all_dependencies(self, step_id: str, dep_graph: Dict[str, List[str]]) -> Set[str]:
        """Get all dependencies recursively."""
        deps = set()
        for dep in dep_graph.get(step_id, []):
            deps.add(dep)
            deps.update(self._get_all_dependencies(dep, dep_graph))
        return deps
    
    def _identify_successful_assignments(self,
                                      schedule: List[ScheduledTask],
                                      steps: List[ProductionStep]) -> Set[LockedAssignment]:
        """Identify assignments that satisfy all constraints."""
        successful = set()
        
        # First, lock steps with no dependencies
        no_dep_steps = {s.step_id for s in steps if not s.depends_on}
        
        # Track station activities
        station_activities = {}  # (station_id, day) -> List[(time_slot, activity_id)]
        
        for task in sorted(schedule, key=lambda t: (t.day, t.time_slot)):
            step = next((s for s in steps if s.step_id == task.step_id), None)
            if not step:
                continue
                
            key = (task.station_id, task.day)
            if key not in station_activities:
                station_activities[key] = []
            station_activities[key].append((task.time_slot, step.activity_id))
            
            if (task.step_id in no_dep_steps or 
                all(dep in {l.step_id for l in self.locked_assignments}
                    for dep in step.depends_on)):
                successful.add(LockedAssignment(
                    step_id=task.step_id,
                    station_id=task.station_id,
                    day=task.day,
                    time_slot=task.time_slot,
                    activity_id=step.activity_id,
                    employee_id=task.employee_id
                ))
        
        return successful
    
    def _score_schedule(self, scheduled_tasks: List[ScheduledTask]) -> float:
        """Score the schedule based on utilization, efficiency, and activity changes."""
        if not scheduled_tasks:
            return 0.0
            
        # Calculate utilization metrics
        shift_usage = {"AM": 0, "PM": 0}
        station_shifts = {}  # (station_id, day) -> set(shifts)
        day_usage = {}  # day -> count of tasks
        station_usage = {}  # station_id -> count of tasks
        
        for task in scheduled_tasks:
            # Track shift usage
            shift_usage[task.time_slot] += 1
            
            # Track station shifts
            key = (task.station_id, task.day)
            if key not in station_shifts:
                station_shifts[key] = set()
            station_shifts[key].add(task.time_slot)
            
            # Track daily usage
            if task.day not in day_usage:
                day_usage[task.day] = 0
            day_usage[task.day] += 1
            
            # Track station usage
            if task.station_id not in station_usage:
                station_usage[task.station_id] = 0
            station_usage[task.station_id] += 1
        
        # Base scores
        total_slots = 12 * 10  # stations * days per shift
        am_utilization = shift_usage["AM"] / total_slots
        pm_utilization = shift_usage["PM"] / total_slots
        
        # Penalties
        daily_penalty = sum((24 - count) * 20 for count in day_usage.values())  # Increased penalty
        shift_imbalance_penalty = abs(am_utilization - pm_utilization) * 100  # Increased penalty
        station_underuse_penalty = sum((20 - count) * 15 for count in station_usage.values())  # New penalty
        
        # Bonuses
        full_day_bonus = sum(1 for shifts in station_shifts.values() if len(shifts) == 2) * 10
        high_utilization_bonus = len(scheduled_tasks) * 5  # Reward for each scheduled task
        
        # Track activity changes
        activity_changes = {}  # station_id -> count of changes
        current_activities = {}  # station_id -> (activity_id, day, time_slot)
        
        for task in sorted(scheduled_tasks, key=lambda t: (t.day, t.time_slot)):
            if task.station_id not in current_activities:
                current_activities[task.station_id] = (task.activity_id, task.day, task.time_slot)
                activity_changes[task.station_id] = 0
            else:
                prev_activity, prev_day, prev_slot = current_activities[task.station_id]
                if prev_activity != task.activity_id:
                    activity_changes[task.station_id] += 1
                current_activities[task.station_id] = (task.activity_id, task.day, task.time_slot)
        
        # Calculate activity change penalties
        activity_change_penalty = sum(changes * 10 for changes in activity_changes.values())
        
        # Calculate final score
        score = ((am_utilization + pm_utilization) / 2) * 2000  # Base utilization (doubled)
        score += full_day_bonus + high_utilization_bonus
        score -= (daily_penalty + shift_imbalance_penalty + station_underuse_penalty + activity_change_penalty)
        
        return max(0, score)  # Ensure non-negative

    def _format_violation_history(self, violations: List[Dict]) -> str:
        """Format violation history for agent prompts."""
        if not violations:
            return "No previous violations."
            
        formatted = []
        for record in violations:
            iteration = record['iteration']
            for v in record['violations']:
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

    def _adjust_steps_from_violations(self, steps: List[ProductionStep], violations: List[Dict]) -> List[ProductionStep]:
        """Adjust steps to schedule based on specific violations."""
        problem_steps = set()
        
        for violation in violations:
            if violation['type'] == 'dependency_violation':
                problem_steps.add(violation['step_id'])
                problem_steps.add(violation['related_step_id'])
            elif violation['type'] in ['employee_unavailable', 'station_conflict', 'slot_conflict', 'worker_overload']:
                problem_steps.add(violation['step_id'])
            elif violation['type'] == 'setup_teardown_violation':
                # For setup/teardown violations, reschedule both affected steps
                problem_steps.add(violation['step_id'])
                if 'related_step_id' in violation:
                    problem_steps.add(violation['related_step_id'])
        
        return [step for step in steps if step.step_id not in problem_steps] 

    def _print_schedule(self, tasks: List[ScheduledTask]):
        """Print schedule in a readable format."""
        if not tasks:
            print("No tasks scheduled")
            return
            
        # Group by day and shift
        schedule = {}  # (day, slot) -> List[tasks]
        for task in sorted(tasks, key=lambda t: (t.day, t.time_slot)):
            key = (task.day, task.time_slot)
            if key not in schedule:
                schedule[key] = []
            schedule[key].append(task)
        
        # Track cumulative progress
        completed_units = {}  # step_id -> set(completed units)
        
        # Get all POs and their steps
        po_lookup = {}  # po_id -> PurchaseOrder
        for po in self.step_sequencer.purchase_orders:
            po_lookup[po.id] = po
        
        for (day, slot), shift_tasks in sorted(schedule.items()):
            # Print date and shift separately to avoid parsing issues
            print(f"\nDate: {day.isoformat()}")
            print(f"Shift: {slot}")
            for task in sorted(shift_tasks, key=lambda t: t.station_id):
                step = next((s for s in self.production_steps if s.step_id == task.step_id), None)
                print(
                    f"  Station {task.station_id}: "
                    f"Step {task.step_id} "
                    f"(Activity {task.activity_id}, "
                    f"Units {task.units_start}-{task.units_end}, "
                    f"Worker {task.employee_id or 'unassigned'})"
                )
                
                # Update completed units
                if task.step_id not in completed_units:
                    completed_units[task.step_id] = set()
                completed_units[task.step_id].update(range(task.units_start, task.units_end + 1))
            
            # Print progress after each shift
            print("\n  Progress:")
            for po_id in sorted({t.purchase_order_id for t in tasks}):
                po = po_lookup[po_id]  # Get actual PO object
                po_steps = [s for s in self.production_steps if s.purchase_order_id == po_id]
                progress, active_steps = self.step_sequencer._calculate_po_progress(
                    po, po_steps, completed_units
                )
                print(f"    Order {po.id}: {progress:.1f}% complete "
                      f"({active_steps}/{len(po_steps)} steps active)")

    def validate_schedule(self, schedule: List[ScheduledTask]) -> bool:
        """Validate schedule has all required assignments."""
        for task in schedule:
            if not task.station_id:
                raise ValueError(f"Task {task.step_id} has no station assigned")
            if not task.employee_id:
                raise ValueError(f"Task {task.step_id} has no worker assigned")
            if not task.activity_id:
                raise ValueError(f"Task {task.step_id} has no activity assigned")
        return True 