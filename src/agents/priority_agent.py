from typing import List, Dict
import datetime
import json
from crewai import Task, Crew
from .base_agent import BaseAgent
from ..models.purchase_order import PurchaseOrder
from ..models.production_step import ProductionStep
from ..config import STATIONS_PER_DAY

class PriorityAgent(BaseAgent):
    """
    Agent responsible for analyzing and adjusting priorities based on current state.
    """
    
    def __init__(self):
        super().__init__(
            name="Priority Analyzer",
            role="Production Priority Specialist",
            goal="Optimize order priorities based on multiple factors",
            backstory="""
            Expert in production scheduling and priority management.
            Analyzes multiple factors to determine optimal priorities
            while considering deadlines, dependencies, and resource constraints.
            """
        )
    
    def update_priorities(self,
                         purchase_orders: List[PurchaseOrder],
                         steps: List[ProductionStep],
                         previous_reasoning: str = None,
                         previous_violations: List[Dict] = None) -> None:
        """Update priorities for our three orders (PO-101, PO-102, PO-103)."""
        
        # Build dependency graph
        dep_graph = self._build_dependency_graph(steps)
        critical_paths = self._find_critical_paths(steps, dep_graph)
        
        for po in purchase_orders:
            # Base priority (0-100)
            base_score = po.base_priority
            
            # Deadline factor (-20 to +20)
            days_until_due = (po.due_date - datetime.date.today()).days
            deadline_score = 20 - (days_until_due * 2)
            
            # Value factor (0 to 15)
            max_value = max(p.value for p in purchase_orders)
            value_score = (po.value / max_value) * 15
            
            # Calculate final priority
            po.effective_priority = min(100, max(1,
                base_score +
                deadline_score +
                value_score
            ))
            
            print(f"Updated {po.id} priority to {po.effective_priority}")
            print(f"- Base: {base_score}")
            print(f"- Deadline ({days_until_due} days): {deadline_score}")
            print(f"- Value (${po.value:,}): {value_score}")
    
    def _build_dependency_graph(self, steps: List[ProductionStep]) -> Dict[str, List[str]]:
        """Build graph of step dependencies."""
        graph = {}
        for step in steps:
            graph[step.step_id] = []
            for other in steps:
                if step.step_id in other.depends_on:
                    graph[step.step_id].append(other.step_id)
        return graph
    
    def _find_critical_paths(self, steps: List[ProductionStep], 
                           dep_graph: Dict[str, List[str]]) -> List[List[ProductionStep]]:
        """Find critical paths in dependency graph."""
        critical_paths = []
        start_steps = [s for s in steps if not s.depends_on]
        
        for start in start_steps:
            path = [start]
            while True:
                current = path[-1]
                next_steps = [s for s in steps if s.step_id in dep_graph[current.step_id]]
                if not next_steps:
                    if len(path) > 2:  # Only consider significant paths
                        critical_paths.append(path.copy())
                    break
                path.append(max(next_steps, key=lambda s: s.duration_days))
        
        return critical_paths
    
    def _calculate_processing_times(self, steps: List[ProductionStep]) -> Dict[str, float]:
        """Calculate total processing time needed for each PO."""
        times = {}
        for step in steps:
            if step.purchase_order_id not in times:
                times[step.purchase_order_id] = 0
            # Include setup and teardown times
            times[step.purchase_order_id] += (
                step.duration_days +
                step.setup_time_days +
                step.teardown_time_days
            )
        return times
    
    def _count_violations(self, po_id: str, violations: List[Dict]) -> int:
        """Count violations related to this PO."""
        if not violations:
            return 0
            
        count = 0
        for record in violations:
            for violation in record['violations']:
                if 'step_id' in violation:
                    step_id = violation['step_id']
                    if step_id.startswith(f"ST-{po_id}"):
                        count += 1
        return count

    def _calculate_critical_paths(self, purchase_orders: List[PurchaseOrder], steps: List[ProductionStep]) -> Dict:
        critical_paths = {}
        
        # Group steps by PO
        po_steps = {}
        for step in steps:
            if step.purchase_order_id not in po_steps:
                po_steps[step.purchase_order_id] = []
            po_steps[step.purchase_order_id].append(step)
        
        for po in purchase_orders:
            if po.id not in po_steps:
                continue
                
            # Calculate earliest possible completion time for each step
            earliest_completion = {}  # step_id -> (time, path)
            steps_to_process = po_steps[po.id].copy()
            
            # Start with steps that have no dependencies
            ready_steps = [s for s in steps_to_process if not s.depends_on]
            for step in ready_steps:
                # Calculate time considering units and parallel processing
                total_units = po.units
                parallel_batches = (total_units + step.units_per_station - 1) // step.units_per_station
                processing_time = parallel_batches * step.duration_days + step.setup_time_days + step.teardown_time_days
                earliest_completion[step.step_id] = (processing_time, [step.step_id])
                steps_to_process.remove(step)
            
            # Process remaining steps
            while steps_to_process:
                next_steps = []
                for step in steps_to_process:
                    # Check if all dependencies are processed
                    if all(dep in earliest_completion for dep in step.depends_on):
                        # Find the latest completing dependency
                        dep_times = [(earliest_completion[dep][0], dep) for dep in step.depends_on]
                        latest_dep_time, critical_dep = max(dep_times, key=lambda x: x[0])
                        
                        # Calculate this step's completion time
                        total_units = po.units
                        parallel_batches = (total_units + step.units_per_station - 1) // step.units_per_station
                        processing_time = parallel_batches * step.duration_days + step.setup_time_days + step.teardown_time_days
                        
                        # Consider minimum units needed to start
                        if step.min_units_to_start > 1:
                            # Add time for initial units to complete
                            initial_batch_time = (step.min_units_to_start / step.units_per_station) * step.duration_days
                            processing_time += initial_batch_time
                        
                        total_time = latest_dep_time + processing_time
                        critical_path = earliest_completion[critical_dep][1] + [step.step_id]
                        
                        earliest_completion[step.step_id] = (total_time, critical_path)
                        next_steps.append(step)
                
                for step in next_steps:
                    steps_to_process.remove(step)
            
            # Find the overall critical path
            if earliest_completion:
                latest_time, critical_path = max(earliest_completion.values(), key=lambda x: x[0])
                critical_paths[po.id] = {
                    'total_time': latest_time,
                    'path': critical_path,
                    'units': po.units
                }
        
        return critical_paths

    def _format_critical_paths(self, critical_paths: Dict) -> str:
        formatted = []
        for po_id, data in critical_paths.items():
            formatted.append(
                f"PO {po_id} ({data['units']} units):\n"
                f"- Critical Path: {' -> '.join(data['path'])}\n"
                f"- Minimum Time: {data['total_time']:.1f} days"
            )
        return "\n".join(formatted)

    def _format_processing_rates(self, steps: List[ProductionStep]) -> str:
        rates = []
        for step in steps:
            rates.append(
                f"Step {step.step_id}: {step.units_per_station} units/station/slot, "
                f"needs {step.min_units_to_start} units complete to start"
            )
        return "\n".join(rates)

    def _format_production_requirements(self, purchase_orders: List[PurchaseOrder], steps: List[ProductionStep]) -> str:
        reqs = []
        for po in purchase_orders:
            po_steps = [s for s in steps if s.purchase_order_id == po.id]
            total_processing = sum(
                step.duration_days * ((po.units + step.units_per_station - 1) // step.units_per_station)
                for step in po_steps
            )
            reqs.append(
                f"PO {po.id}:\n"
                f"- {po.units} units needed\n"
                f"- Due in {(po.due_date - datetime.date.today()).days} days\n"
                f"- Total processing: {total_processing:.1f} days (if sequential)"
            )
        return "\n".join(reqs)

    def _format_pos_for_prompt(self, purchase_orders: List[PurchaseOrder]) -> str:
        """Format POs into a string for the prompt."""
        return "\n".join([
            f"- ID: {po.id}, Due: {po.due_date}, "
            f"Base Priority: {po.base_priority}, Value: ${po.value}"
            for po in purchase_orders
        ])

    def _format_priority_assessment(self, purchase_orders: List[PurchaseOrder], steps: List[ProductionStep]) -> str:
        """Format priority assessment in a clear, structured way."""
        assessments = []
        assessments.append("**Priority Assessment**:\n")
        
        for po in purchase_orders:
            po_steps = [s for s in steps if s.purchase_order_id == po.id]
            days_to_due = (po.due_date - datetime.date.today()).days
            
            assessment = f"**Order {po.id}**:\n"
            assessment += f"  - Due Date: {po.due_date} ({days_to_due} days) - Score: {min(10, max(1, 10 - days_to_due))}\n"
            assessment += f"  - Size: {po.units} units ({len(po_steps)} steps) - Score: {min(10, po.units // 5)}\n"
            assessment += f"  - Value: ${po.value:,} - Score: {min(10, po.value // 10000)}\n"
            assessment += f"  - Base Priority: {po.base_priority} - Score: {po.base_priority // 10}\n"
            
            # Calculate critical path length
            critical_path = self._find_critical_path(po_steps)
            assessment += f"  - Critical Path Length: {len(critical_path)} steps - Score: {min(10, len(critical_path))}\n"
            
            assessments.append(assessment)
        
        return "\n".join(assessments)

    def _format_sequence_plan(self, purchase_orders: List[PurchaseOrder], steps: List[ProductionStep]) -> str:
        """Format a clear sequence plan for our 3 orders."""
        plan = ["### Sequence Plan\n"]
        
        # Sort orders by effective priority
        sorted_orders = sorted(purchase_orders, key=lambda po: po.effective_priority, reverse=True)
        
        for po in sorted_orders:
            po_steps = [s for s in steps if s.purchase_order_id == po.id]
            days_to_due = (po.due_date - datetime.date.today()).days
            
            if po.effective_priority >= 80:
                category = "Critical Orders"
            elif po.effective_priority >= 60:
                category = "High Priority Orders"
            else:
                category = "Standard Orders"
                
            plan.append(f"**{category}**:")
            plan.append(f"- **Order {po.id}**:")
            plan.append(f"  - {po.units} units due in {days_to_due} days")
            plan.append(f"  - Value: ${po.value:,}")
            plan.append(f"  - Priority Score: {po.effective_priority}")
            plan.append(f"  - Steps: {len(po_steps)}")
            
            # Add reasoning
            plan.append(f"  *Reasoning: Based on {days_to_due} day deadline, "
                       f"${po.value:,} value, and {len(po_steps)} production steps.*\n")
        
        return "\n".join(plan) 