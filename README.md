# Klaedo MVP - AI-Powered Production Scheduling System

Klaedo is an intelligent production scheduling system that uses multiple AI agents to create and optimize manufacturing schedules. It handles complex constraints like dependencies, resource availability, and unit-based processing while maximizing parallel production.

## Architecture

The system uses a multi-agent architecture with specialized AI agents:

1. **Priority Agent** (`PriorityAgent`)
   - Analyzes purchase orders and production steps
   - Calculates critical paths and dependencies
   - Assigns dynamic priorities based on deadlines, value, and complexity

2. **Step Sequencer** (`StepSequencer`)
   - Creates initial production schedules
   - Handles parallel processing across stations
   - Manages unit-based production tracking
   - Ensures full utilization of available capacity

3. **Resource Assigner** (`ResourceAssigner`)
   - Matches workers to scheduled tasks
   - Considers worker skills and availability
   - Balances workload across shifts
   - Tracks unit processing times

4. **Constraints Agent** (`ConstraintsAgent`)
   - Validates schedule feasibility
   - Checks dependencies and timing
   - Verifies resource availability
   - Ensures unit completion requirements

5. **Refinement Agent** (`RefinementAgent`)
   - Optimizes feasible schedules
   - Improves parallel processing
   - Minimizes setup/teardown overhead
   - Balances station utilization

## Key Features

### Production Management
- Unit-based processing tracking
- Parallel processing across stations
- Minimum units required to start steps
- Setup and teardown time handling
- Activity-based station configuration

### Resource Optimization
- Worker skill matching
- Shift balance optimization
- Station utilization tracking
- Workload distribution
- Capacity planning

### Scheduling Intelligence
- Critical path analysis
- Dynamic priority adjustment
- Dependency management
- Constraint validation
- Schedule refinement

### Schedule Generation
- 10-day scheduling horizon
- AM/PM shift planning
- 12 stations per shift
- Full station utilization
- Idle task management

## Data Models

### Purchase Order
```python
PurchaseOrder(
    id="PO-101",           # Order identifier
    due_date="2024-03-25", # Delivery deadline
    units=50,              # Total units needed
    value=25000,           # Order value in dollars
    base_priority=80       # Initial priority (1-100)
)
```

### Production Step
```python
ProductionStep(
    step_id="ST-1",           # Step identifier
    purchase_order_id="PO-1", # Associated order
    activity_id="ACT-1",      # Required activity
    step_order=1,             # Sequence number
    depends_on=["ST-2"],      # Prerequisite steps
    duration_days=0.25,       # Processing time per unit
    setup_time_days=0.125,    # Setup time needed
    teardown_time_days=0.125, # Teardown time needed
    units_per_station=5,      # Units processed in parallel
    min_units_to_start=2      # Units needed to begin next step
)
```

### Activity
```python
Activity(
    id="ACT-1",              # Activity identifier
    name="Panel Assembly",    # Activity description
    required_skills=["S1"],   # Required worker skills
    setup_time_days=0.125,    # Default setup time
    teardown_time_days=0.125  # Default teardown time
)
```

### Employee
```python
Employee(
    id="EMP-1",                    # Employee identifier
    name="John Smith",             # Employee name
    skills=["S1", "S2"],          # Qualified activities
    availability=["2024-03-19"],   # Available dates
    max_shifts_per_day=2          # Shift limit per day
)
```

### Station
```python
Station(
    id="S1",                    # Station identifier
    current_activity_id="ACT-1" # Currently configured activity
)
```

## Real-World Example: Lighting Manufacturer

Consider a lighting manufacturer with 12 production stations running over 10 days. They produce custom LED fixtures with the following workflow:

### Activities
1. **Panel Assembly** (ACT-1)
   - Assembling LED panels
   - Requires electrical assembly skills
   - 5 units processed per station per shift

2. **Housing Assembly** (ACT-2)
   - Building fixture housings
   - Requires mechanical assembly skills
   - 4 units processed per station per shift

3. **Integration** (ACT-3)
   - Combining panels and housings
   - Requires both skill sets
   - 3 units processed per station per shift

4. **Testing** (ACT-4)
   - Quality control and certification
   - Requires testing certification
   - 6 units tested per station per shift

### Current Orders
1. **Large Office Building (PO-101)**
   - 200 Premium LED Panels
   - Due in 7 days
   - High priority (90)
   - Value: $100,000

2. **Retail Chain (PO-102)**
   - 150 Standard Fixtures
   - Due in 10 days
   - Medium priority (70)
   - Value: $45,000

3. **Hospital Renovation (PO-103)**
   - 100 Medical-Grade Fixtures
   - Due in 5 days
   - Urgent priority (95)
   - Value: $80,000

### Production Flow
1. Each fixture requires:
   - Panel Assembly (0.25 days/unit)
   - Housing Assembly (0.25 days/unit)
   - Integration (0.5 days/unit)
   - Testing (0.125 days/unit)

2. Dependencies:
   - Integration needs 5 completed panels and housings
   - Testing can start after 3 integrated units

3. Station Setup:
   - 12 flexible stations
   - AM/PM shifts
   - 0.125 days for activity changes

The system will create a schedule maximizing parallel production while respecting:
- Worker skills and availability
- Station capacity and setup times
- Unit dependencies between steps
- Priority order completion

## Example Usage

```python
from src.orchestrator import SchedulingOrchestrator
from src.agents import *
from src.models import *

# Initialize agents
priority_agent = PriorityAgent()
step_sequencer = StepSequencer(stations, dates)
resource_assigner = ResourceAssigner(employees)
constraints_agent = ConstraintsAgent()
refinement_agent = RefinementAgent()

# Create orchestrator
orchestrator = SchedulingOrchestrator(
    priority_agent=priority_agent,
    step_sequencer=step_sequencer,
    resource_assigner=resource_assigner,
    constraints_agent=constraints_agent,
    refinement_agent=refinement_agent
)

# Generate schedule
schedule = orchestrator.run_scheduling_loop(
    purchase_orders=purchase_orders,
    production_steps=steps,
    employees=employees
)
```

## Schedule Output Format

Each scheduled task contains:
```python
ScheduledTask(
    step_id="ST-1",          # Production step ID
    station_id="S1",         # Station assigned
    day="2024-03-19",        # Scheduled date
    time_slot="AM",          # AM or PM shift
    purchase_order_id="PO-1", # Associated PO
    activity_id="ACT-1",     # Activity type
    units_start=1,           # Starting unit
    units_end=5,             # Ending unit
    employee_id="EMP-1"      # Assigned worker
)
```

## Configuration

Key system parameters in `config.py`:
```python
STATIONS_PER_DAY = 12        # Stations available per shift
WORKERS_PER_STATION = 1      # Workers needed per station
MAX_WORKER_TASKS_PER_DAY = 2 # Max shifts per worker per day
```

## Dependencies
- Python 3.8+
- CrewAI
- Other requirements in requirements.txt

## Installation
```bash
pip install -r requirements.txt
``` 