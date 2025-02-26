import datetime
from .config import config
from .models.activity import Activity
from .models.station import Station
from .models.employee import Employee
from .models.purchase_order import PurchaseOrder
from .models.production_step import ProductionStep
from .models.scheduled_task import ScheduledTask
from .agents.priority_agent import PriorityAgent
from .agents.constraints_agent import ConstraintsAgent
from .agents.step_sequencer import StepSequencer
from .agents.resource_assigner import ResourceAssigner
from .agents.refinement_agent import RefinementAgent
from .orchestrator import SchedulingOrchestrator
from .example_data import (
    create_activities,
    create_stations,
    create_employees,
    create_purchase_orders,
    create_production_steps
)
from typing import List
from .utils.logging import setup_logging

def main():
    # Setup logging first
    setup_logging()
    
    # Log initial configuration and data
    print("\n=== INITIAL CONFIGURATION AND DATA ===\n")
    
    # Load example data
    activities = create_activities()
    stations = create_stations()
    today = datetime.date.today()
    dates = [today + datetime.timedelta(days=i) for i in range(10)]
    employees = create_employees(dates)
    purchase_orders = create_purchase_orders(today)
    production_steps = create_production_steps()
    
    # Log activities
    print("\nActivities:")
    for activity in activities:
        print(f"  {activity.id}: {activity.description}")  # Changed from name to description
    
    # Log stations
    print("\nStations:")
    for station in stations:
        print(f"  {station.id}: Currently set up for {station.current_activity_id or 'None'}")
    
    # Log employees
    print("\nEmployees:")
    for emp in employees:
        print(f"  {emp.name} (ID: {emp.id})")
        print(f"    Skills: {emp.skills}")
        print(f"    Available: {len(emp.availability)} days")
        print(f"    Max Shifts/Day: {emp.max_shifts_per_day}")
    
    # Log purchase orders
    print("\nPurchase Orders:")
    for po in purchase_orders:
        print(f"  {po.id}:")
        print(f"    Units: {po.units}")
        print(f"    Due Date: {po.due_date}")
        print(f"    Value: ${po.value:,.2f}")
        print(f"    Base Priority: {po.base_priority}")
    
    # Log production steps
    print("\nProduction Steps:")
    for step in production_steps:
        print(f"  {step.step_id}:")
        print(f"    PO: {step.purchase_order_id}")
        print(f"    Activity: {step.activity_id}")
        print(f"    Dependencies: {step.depends_on}")
        print(f"    Units/Station: {step.units_per_station}")
        print(f"    Min Units to Start: {step.min_units_to_start}")
    
    print("\n=== SCHEDULING PROCESS BEGINS ===\n")

    # Validate configuration
    if not config.validate():
        print("Error: Invalid configuration. Please check your .env file.")
        return

    # Load example data
    activities = create_activities()
    stations = create_stations()
    
    # Create date range for schedule (next 10 days)
    today = datetime.date.today()
    dates = [today + datetime.timedelta(days=i) for i in range(10)]
    
    # Load remaining data
    employees = create_employees(dates)
    purchase_orders = create_purchase_orders(today)
    production_steps = create_production_steps()
    
    # Initialize agents
    priority_agent = PriorityAgent()
    constraints_agent = ConstraintsAgent()
    step_sequencer = StepSequencer(station_list=stations, date_list=dates)
    resource_assigner = ResourceAssigner(employees=employees)
    refinement_agent = RefinementAgent()
    
    # Create orchestrator
    orchestrator = SchedulingOrchestrator(
        priority_agent=priority_agent,
        step_sequencer=step_sequencer,
        resource_assigner=resource_assigner,
        constraints_agent=constraints_agent,
        refinement_agent=refinement_agent
    )
    
    # Run scheduling process
    final_schedule, is_feasible = orchestrator.run_scheduling_loop(
        purchase_orders=purchase_orders,
        production_steps=production_steps,
        employees=employees
    )
    
    # Calculate and display shift utilization
    print("\n=== Schedule Statistics ===")
    print(f"Schedule Feasibility: {'FEASIBLE' if is_feasible else 'UNFEASIBLE'}")
    
    shift_usage = {"AM": 0, "PM": 0}
    station_shifts = {}  # (station_id, day) -> set(shifts)
    worker_assignments = {}  # employee_id -> count
    
    for task in final_schedule:
        # Shift usage
        shift_usage[task.time_slot] += 1
        
        # Station usage
        key = (task.station_id, task.day)
        if key not in station_shifts:
            station_shifts[key] = set()
        station_shifts[key].add(task.time_slot)
        
        # Worker assignments
        if task.employee_id:
            worker_assignments[task.employee_id] = worker_assignments.get(task.employee_id, 0) + 1
    
    total_slots = 12 * 10  # stations * days per shift
    print("\nUtilization:")
    print(f"AM Shift: {(shift_usage['AM'] / total_slots) * 100:.1f}%")
    print(f"PM Shift: {(shift_usage['PM'] / total_slots) * 100:.1f}%")
    print(f"Overall: {((shift_usage['AM'] + shift_usage['PM']) / (total_slots * 2)) * 100:.1f}%")
    
    print("\nSchedule Metrics:")
    print(f"Total Tasks: {len(final_schedule)}")
    print(f"Stations Used Both Shifts: {sum(1 for shifts in station_shifts.values() if len(shifts) == 2)}")
    print(f"Workers Assigned: {len(worker_assignments)} of {len(employees)}")
    print(f"Unassigned Tasks: {sum(1 for t in final_schedule if not t.employee_id)}")
    
    # Print detailed schedule report
    print_schedule_report(
        final_schedule, 
        employees, 
        production_steps,
        purchase_orders
    )

def print_schedule_report(schedule: List[ScheduledTask], 
                         employees: List[Employee], 
                         steps: List[ProductionStep],
                         purchase_orders: List[PurchaseOrder]):
    """Print detailed schedule report with shift and activity analysis."""
    print("\n=== Schedule Report ===")
    
    # Track order progress
    order_progress = {}  # (po_id, day) -> {step_id: completed_units}
    order_total_units = {}  # po_id -> total_units
    order_steps = {}  # po_id -> set(step_ids)
    
    # Initialize tracking
    for step in steps:
        if step.purchase_order_id not in order_steps:
            order_steps[step.purchase_order_id] = set()
        order_steps[step.purchase_order_id].add(step.step_id)
    
    # Group by day and shift
    day_shift_tasks = {}
    for task in sorted(schedule, key=lambda t: (t.day, t.time_slot)):
        key = (task.day, task.time_slot)
        if key not in day_shift_tasks:
            day_shift_tasks[key] = []
        day_shift_tasks[key].append(task)
        
        # Track progress
        po_id = task.purchase_order_id
        if po_id not in order_progress:
            order_progress[po_id] = {}
        if task.day not in order_progress[po_id]:
            order_progress[po_id][task.day] = {}
        if task.step_id not in order_progress[po_id][task.day]:
            order_progress[po_id][task.day][task.step_id] = set()
        
        # Add completed units
        order_progress[po_id][task.day][task.step_id].update(
            range(task.units_start, task.units_end + 1)
        )
    
    # Print schedule by day/shift with order progress
    current_day = None
    for (day, shift), tasks in sorted(day_shift_tasks.items()):
        print(f"\n{day} - {shift} Shift:")
        for task in sorted(tasks, key=lambda t: t.station_id):
            emp = next((e for e in employees if e.id == task.employee_id), None)
            emp_name = emp.name if emp else "Unassigned"
            step = next((s for s in steps if s.step_id == task.step_id), None)
            activity = step.activity_id if step else "Unknown"
            print(f"  Station {task.station_id} (Activity {activity}): {task.step_id} ({emp_name})")
        
        # Print order progress at end of day
        if shift == "PM" and day != current_day:
            current_day = day
            print(f"\n  End of Day Progress:")
            for po_id, days in order_progress.items():
                if day in days:  # Only show active orders
                    total_steps = len(order_steps[po_id])
                    completed_steps = 0
                    total_units = 0
                    
                    # Get total units needed for this PO
                    po_total_units = next(po.units for po in purchase_orders if po.id == po_id)
                    
                    # Count completed steps and units
                    for step_id in order_steps[po_id]:
                        units = len(days[day].get(step_id, set()))
                        if units > 0:
                            total_units += units
                            completed_steps += 1
                    
                    if completed_steps > 0:  # Only show if order had activity
                        avg_completion = (total_units / (total_steps * po_total_units)) * 100
                        print(f"    Order {po_id}: {avg_completion:.1f}% complete "
                              f"({completed_steps}/{total_steps} steps active)")
    
    # Print station activity changes
    print("\n=== Station Activity Changes ===")
    for station_id in sorted({t.station_id for t in schedule}):
        print(f"\nStation {station_id} activities:")
        station_tasks = sorted(
            [t for t in schedule if t.station_id == station_id],
            key=lambda t: (t.day, t.time_slot)
        )
        for task in station_tasks:
            step = next((s for s in steps if s.step_id == task.step_id), None)
            activity = step.activity_id if step else "Unknown"
            print(f"  {task.day} {task.time_slot}: Activity {activity}")

if __name__ == "__main__":
    main() 