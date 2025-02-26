from typing import Set

class Orchestrator:
    def _identify_successful_assignments(self, ...) -> Set[LockedAssignment]:
        successful = set()
        
        for task in schedule:
            if (task.step_id in no_dep_steps or 
                all(dep in {l.step_id for l in self.locked_assignments}
                    for step in steps 
                    if step.step_id == task.step_id
                    for dep in step.depends_on)):
                successful.add(LockedAssignment(
                    step_id=task.step_id,
                    station_id=task.station_id,
                    day=task.day,
                    time_slot=task.time_slot,
                    employee_id=task.employee_id
                )) 