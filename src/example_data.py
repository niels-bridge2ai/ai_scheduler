import datetime
from typing import List
from .models.activity import Activity
from .models.station import Station
from .models.employee import Employee
from .models.purchase_order import PurchaseOrder
from .models.production_step import ProductionStep

def create_activities() -> List[Activity]:
    """Create fixed set of production activities."""
    return [
        Activity("A1", "Panel Assembly"),        # Electrical assembly
        Activity("A2", "Circuit Board Prep"),    # Electronics
        Activity("A3", "Housing Assembly"),      # Mechanical assembly
        Activity("A4", "Wiring"),               # Electrical
        Activity("A5", "Testing"),              # Quality control
        Activity("A6", "Packaging"),            # General
        Activity("A7", "PCB Assembly"),         # Electronics
        Activity("A8", "Quality Inspection"),   # Quality control
    ]

def create_stations() -> List[Station]:
    """Create 12 stations with logical initial setup."""
    return [
        Station("S1", "A1"),  # Panel Assembly station
        Station("S2", "A1"),  # Panel Assembly station
        Station("S3", "A2"),  # Circuit Board station
        Station("S4", "A2"),  # Circuit Board station
        Station("S5", "A3"),  # Housing Assembly station
        Station("S6", "A3"),  # Housing Assembly station
        Station("S7", "A4"),  # Wiring station
        Station("S8", "A4"),  # Wiring station
        Station("S9", "A5"),  # Testing station
        Station("S10", "A5"), # Testing station
        Station("S11", "A8"), # Quality Inspection station
        Station("S12", "A6"), # Packaging station
    ]

def create_employees(dates: List[datetime.date]) -> List[Employee]:
    """Create employees with logical skill distribution."""
    employees = []
    
    # Electrical specialists (A1, A4)
    for i in range(1, 4):  # 3 electrical specialists
        employees.append(
            Employee(
                id=f"E{i}",
                name=f"Electrical Specialist {i}",
                skills={"A1", "A4"},
                availability=set(dates)
            )
        )
    
    # Electronics specialists (A2, A7)
    for i in range(4, 7):  # 3 electronics specialists
        employees.append(
            Employee(
                id=f"E{i}",
                name=f"Electronics Specialist {i}",
                skills={"A2", "A7"},
                availability=set(dates)
            )
        )
    
    # Mechanical specialists (A3)
    for i in range(7, 10):  # 3 mechanical specialists
        employees.append(
            Employee(
                id=f"E{i}",
                name=f"Mechanical Specialist {i}",
                skills={"A3"},
                availability=set(dates)
            )
        )
    
    # Quality control specialists (A5, A8)
    for i in range(10, 13):  # 3 QC specialists
        employees.append(
            Employee(
                id=f"E{i}",
                name=f"QC Specialist {i}",
                skills={"A5", "A8"},
                availability=set(dates)
            )
        )
    
    # General workers (A6 + cross-trained)
    for i in range(13, 17):  # 4 general workers
        employees.append(
            Employee(
                id=f"E{i}",
                name=f"General Worker {i}",
                skills={"A6", "A1", "A3"},  # Can help with assembly and packaging
                availability=set(dates)
            )
        )
    
    return employees

def create_purchase_orders(start_date: datetime.date) -> List[PurchaseOrder]:
    """Create fixed set of purchase orders with clear priorities."""
    return [
        # High priority, urgent medical equipment
        PurchaseOrder(
            id="PO-101",
            due_date=start_date + datetime.timedelta(days=5),
            base_priority=90,
            value=75000,
            units=20
        ),
        # Medium priority, standard order
        PurchaseOrder(
            id="PO-102",
            due_date=start_date + datetime.timedelta(days=8),
            base_priority=70,
            value=45000,
            units=30
        ),
        # Low priority, longer deadline
        PurchaseOrder(
            id="PO-103",
            due_date=start_date + datetime.timedelta(days=10),
            base_priority=50,
            value=30000,
            units=15
        )
    ]

def create_production_steps() -> List[ProductionStep]:
    """Create logical production steps with clear dependencies."""
    steps = []
    
    # Standard production flow for each PO:
    # 1. Panel Assembly (A1)
    # 2. Circuit Board Prep (A2) & Housing Assembly (A3) in parallel
    # 3. PCB Assembly (A7) after Circuit Board Prep
    # 4. Wiring (A4) after Panel and PCB
    # 5. Testing (A5)
    # 6. Quality Inspection (A8)
    # 7. Packaging (A6)
    
    for po_num in [101, 102, 103]:
        po_id = f"PO-{po_num}"
        
        # 1. Panel Assembly
        panel_step = f"ST-{po_num}-1"
        steps.append(
            ProductionStep(
                step_id=panel_step,
                purchase_order_id=po_id,
                activity_id="A1",
                step_order=1,
                duration_days=1.0,
                setup_time_days=0.5,
                teardown_time_days=0.5,
                units_per_station=5,
                min_units_to_start=0,
                depends_on=[]
            )
        )
        
        # 2a. Circuit Board Prep
        circuit_step = f"ST-{po_num}-2"
        steps.append(
            ProductionStep(
                step_id=circuit_step,
                purchase_order_id=po_id,
                activity_id="A2",
                step_order=2,
                duration_days=1.0,
                setup_time_days=0.5,
                teardown_time_days=0.5,
                units_per_station=4,
                min_units_to_start=0,
                depends_on=[]
            )
        )
        
        # 2b. Housing Assembly
        housing_step = f"ST-{po_num}-3"
        steps.append(
            ProductionStep(
                step_id=housing_step,
                purchase_order_id=po_id,
                activity_id="A3",
                step_order=2,
                duration_days=0.25,
                setup_time_days=0.125,
                teardown_time_days=0.125,
                units_per_station=4,
                min_units_to_start=1,
                depends_on=[]
            )
        )
        
        # 3. PCB Assembly
        pcb_step = f"ST-{po_num}-4"
        steps.append(
            ProductionStep(
                step_id=pcb_step,
                purchase_order_id=po_id,
                activity_id="A7",
                step_order=3,
                duration_days=0.25,
                setup_time_days=0.125,
                teardown_time_days=0.125,
                units_per_station=3,
                min_units_to_start=2,
                depends_on=[circuit_step]
            )
        )
        
        # 4. Wiring
        wiring_step = f"ST-{po_num}-5"
        steps.append(
            ProductionStep(
                step_id=wiring_step,
                purchase_order_id=po_id,
                activity_id="A4",
                step_order=4,
                duration_days=0.25,
                setup_time_days=0.125,
                teardown_time_days=0.125,
                units_per_station=3,
                min_units_to_start=2,
                depends_on=[panel_step, pcb_step]
            )
        )
        
        # 5. Testing
        testing_step = f"ST-{po_num}-6"
        steps.append(
            ProductionStep(
                step_id=testing_step,
                purchase_order_id=po_id,
                activity_id="A5",
                step_order=5,
                duration_days=0.125,
                setup_time_days=0.125,
                teardown_time_days=0.125,
                units_per_station=6,
                min_units_to_start=3,
                depends_on=[wiring_step]
            )
        )
        
        # 6. Quality Inspection
        qc_step = f"ST-{po_num}-7"
        steps.append(
            ProductionStep(
                step_id=qc_step,
                purchase_order_id=po_id,
                activity_id="A8",
                step_order=6,
                duration_days=0.125,
                setup_time_days=0.125,
                teardown_time_days=0.125,
                units_per_station=6,
                min_units_to_start=3,
                depends_on=[testing_step]
            )
        )
        
        # 7. Packaging
        steps.append(
            ProductionStep(
                step_id=f"ST-{po_num}-8",
                purchase_order_id=po_id,
                activity_id="A6",
                step_order=7,
                duration_days=0.125,
                setup_time_days=0.125,
                teardown_time_days=0.125,
                units_per_station=8,
                min_units_to_start=3,
                depends_on=[qc_step]
            )
        )
    
    return steps
