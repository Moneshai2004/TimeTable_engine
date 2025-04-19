# This code requires the ortools package. Make sure it's installed in your environment.
# If not available, you can install it via: pip install ortools

from ortools.sat.python import cp_model
import json
import os
from datetime import datetime

class TimetableGenerator:
    def __init__(self, include_free_periods=False):
        # Define days, periods, sections
        self.days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
        self.periods = [
            {"id": 1, "time": "08:30-09:20"},
            {"id": 2, "time": "09:20-10:10"},
            {"id": 3, "time": "10:10-11:00"},
            {"id": 4, "time": "11:15-12:00"},
            {"id": 5, "time": "12:00-12:45"},
            {"id": 6, "time": "13:35-14:25"},
            {"id": 7, "time": "14:25-15:15"}
        ]
        self.sections = ['A', 'B']
        
        # Course definitions: (weekly_count, is_lab, teacher)
        # For labs, the count is the number of lab sessions (each session is 2 consecutive periods)
        self.courses = {
            'PAS': (5, False, 'Ms. Sowmiya'),
            'OS':  (6, False, 'Ms. K.Sudha'),
            'ML':  (5, False, 'Mr. Dinesh Kumar'),
            'FDSA':(5, False, 'Ms. Deepika'),
            'CN':  (6, False, 'Ms. Kirupavathy'),
            'EVS': (4, False, 'Ms. Sophia'),
            'FDSA_LAB': (2, True, 'Ms. Deepika'),    # 2 lab sessions (4 periods total)
            'ML_LAB':   (2, True, 'Mr. Dinesh Kumar'), # 2 lab sessions (4 periods total)
            'PD':  (2, False, 'Ms. Kirupavathy'),
            'LIB': (1, False, 'Ms. Kirupavathy'),
            'ACT': (2, False, 'All Staff')
        }
        
        # Add free periods if requested
        if include_free_periods:
            self.courses['FREE'] = (2, False, 'None')
        
        # Fixed slots for administrative activities
        self.fixed_slots = {
            ('A', 'Tue', 2, 'PD'), ('A', 'Fri', 4, 'PD'),
            ('B', 'Tue', 3, 'PD'), ('B', 'Fri', 5, 'PD'),
            ('A', 'Thu', 6, 'LIB'), ('B', 'Thu', 7, 'LIB'),
            ('A', 'Fri', 7, 'ACT'), ('B', 'Sat', 7, 'ACT')
        }
        
        # Initialize model and variables
        self.model = cp_model.CpModel()
        self.assign = {}
        self.solution = None
        self.include_free_periods = include_free_periods
    
    def generate_variables(self):
        # Decision variables: assign[(sec,day,period,course)] = 1 if course at that slot
        for s in self.sections:
            for d in self.days:
                for p in range(1, 8):  # 1..7
                    for c in self.courses:
                        self.assign[(s,d,p,c)] = self.model.NewBoolVar(f"x_{s}_{d}_{p}_{c}")
    
    def add_constraints(self):
        # 1. Exactly one course per slot per section (or at most one if free periods allowed)
        for s in self.sections:
            for d in self.days:
                for p in range(1, 8):
                    if self.include_free_periods:
                        self.model.Add(sum(self.assign[(s,d,p,c)] for c in self.courses) <= 1)
                    else:
                        self.model.Add(sum(self.assign[(s,d,p,c)] for c in self.courses) == 1)
        
        # 2. Course counts per section - exactly the required number
        for s in self.sections:
            for c,(count,_,_) in self.courses.items():
                self.model.Add(sum(self.assign[(s,d,p,c)] for d in self.days for p in range(1, 8)) == count)
        
        # 3. Teacher conflict across sections: no teacher teaches two slots simultaneously
        for d in self.days:
            for p in range(1, 8):
                for teacher in set(t for _,_,t in self.courses.values() if t != 'None'):
                    self.model.Add(
                        sum(self.assign[(s,d,p,c)]
                            for s in self.sections
                            for c,(_,_,t) in self.courses.items() if t == teacher)
                        <= 1)
        
        # 4. No same theory course twice in one day per section
        theory_courses = [c for c,(cnt,is_lab,_) in self.courses.items() 
                         if not is_lab and c not in ('PD','LIB','ACT','FREE')]
        for s in self.sections:
            for d in self.days:
                for c in theory_courses:
                    self.model.Add(sum(self.assign[(s,d,p,c)] for p in range(1, 8)) <= 1)
        
        # 5. Lab sessions must be scheduled as continuous blocks of two periods
        # Labs can only be in periods 4-5 or 6-7
        lab_courses = [c for c,(cnt,is_lab,_) in self.courses.items() if is_lab]
        valid_lab_slots = [(4, 5), (6, 7)]  # Valid pairs of consecutive periods for labs
        
        for s in self.sections:
            for d in self.days:
                # Only one lab per day per section
                self.model.Add(sum(self.assign[(s,d,p,c)] 
                                  for c in lab_courses 
                                  for p in range(1, 8)) <= 2)  # Max 2 periods for one lab
                
                # For each lab course
                for c in lab_courses:
                    # Lab can only be scheduled in valid slots (periods 4-5 or 6-7)
                    for p1, p2 in valid_lab_slots:
                        # If first period of slot has the lab, second period must also have it
                        self.model.Add(self.assign[(s,d,p1,c)] == self.assign[(s,d,p2,c)])
                    
                    # Lab can only be in valid periods
                    valid_periods = [p for slot in valid_lab_slots for p in slot]
                    for p in range(1, 8):
                        if p not in valid_periods:
                            self.model.Add(self.assign[(s,d,p,c)] == 0)
        
        # 6. Avoid having the same subject in consecutive periods (except for labs)
        for s in self.sections:
            for d in self.days:
                for p in range(1, 7):  # 1..6 (to avoid going out of range)
                    for c in self.courses:
                        if not any(lab in c for lab in ['LAB']):  # Skip this constraint for lab courses
                            # If a course is assigned to period p, it shouldn't be assigned to period p+1
                            self.model.Add(self.assign[(s,d,p,c)] + self.assign[(s,d,p+1,c)] <= 1)
        
        # 7. Fixed slots for administrative activities
        for (s, d, p, c) in self.fixed_slots:
            self.model.Add(self.assign[(s,d,p,c)] == 1)
        
        # 8. If free periods are included, we don't need additional constraints
        # This constraint was making the problem too restrictive
    
    def solve(self):
        # Solve the model
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 120  # Increase time limit for complex problems
        solver.parameters.num_search_workers = 8
        status = solver.Solve(self.model)
        
        # Check if a solution was found
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            print("Solution found!")
            
            # Store the solution
            self.solution = {}
            for s in self.sections:
                self.solution[s] = {}
                for d in self.days:
                    self.solution[s][d] = {}
                    for p in range(1, 8):
                        for c in self.courses:
                            if solver.Value(self.assign[(s,d,p,c)]) == 1:
                                _, _, teacher = self.courses[c]
                                self.solution[s][d][p] = {
                                    "course": c,
                                    "teacher": teacher
                                }
            return True
        else:
            print("No solution found.")
            return False
    
    def print_timetable(self):
        if not self.solution:
            print("No solution to print.")
            return
        
        # Print a separator line
        def print_separator(width=120):
            print('-' * width)
        
        for s in self.sections:
            print_separator()
            print(f"\n{'=' * 30} SECTION {s} TIMETABLE {'=' * 30}")
            print_separator()
            
            # Print header with period times
            header = ['Day'] + [f'P{p} ({self.periods[p-1]["time"]})' for p in range(1, 8)]
            print('{:<8}'.format(header[0]), end=' | ')
            print(' | '.join('{:<16}'.format(h) for h in header[1:]))
            print_separator()
            
            # Print each day's schedule
            for d in self.days:
                row = [d]
                for p in range(1, 8):
                    if p in self.solution[s][d]:
                        course = self.solution[s][d][p]["course"]
                        teacher = self.solution[s][d][p]["teacher"]
                        if teacher == "All Staff":
                            row.append(f"{course}")
                        elif teacher == "None":
                            row.append(f"{course}")
                        else:
                            teacher_short = teacher.split('.')[-1] if '.' in teacher else teacher
                            row.append(f"{course} ({teacher_short})")
                    else:
                        row.append("FREE")  # Free period if no course assigned
                
                print('{:<8}'.format(row[0]), end=' | ')
                print(' | '.join('{:<16}'.format(c) for c in row[1:]))
            
            print_separator()
            print("\n")
        
        # Print statistics
        print("\nTIMETABLE STATISTICS:")
        print_separator()
        
        # Count subject occurrences per section
        for s in self.sections:
            print(f"\nSection {s} Subject Distribution:")
            subject_counts = {}
            for d in self.days:
                for p in range(1, 8):
                    if p in self.solution[s][d]:
                        course = self.solution[s][d][p]["course"]
                        subject_counts[course] = subject_counts.get(course, 0) + 1
            
            for subject, count in sorted(subject_counts.items()):
                required = self.courses[subject][0]
                print(f"{subject:10}: {count:2} periods (Required: {required})")
        
        # Count teacher workload
        print("\nTeacher Workload:")
        teacher_workload = {}
        for s in self.sections:
            for d in self.days:
                for p in range(1, 8):
                    if p in self.solution[s][d]:
                        teacher = self.solution[s][d][p]["teacher"]
                        teacher_workload[teacher] = teacher_workload.get(teacher, 0) + 1
        
        for teacher, count in sorted(teacher_workload.items()):
            print(f"{teacher:15}: {count:2} periods")
    
    def generate_html(self, output_file="timetable.html"):
        if not self.solution:
            print("No solution to generate HTML.")
            return False
        
        # Create HTML content
        html_content = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Class Timetable</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background-color: #f5f5f5;
                }
                .container {
                    max-width: 1200px;
                    margin: 0 auto;
                    background-color: white;
                    padding: 20px;
                    box-shadow: 0 0 10px rgba(0,0,0,0.1);
                    border-radius: 5px;
                }
                h1 {
                    color: #333;
                    text-align: center;
                    margin-bottom: 30px;
                }
                h2 {
                    color: #444;
                    margin-top: 40px;
                    padding-bottom: 10px;
                    border-bottom: 2px solid #eee;
                }
                table {
                    width: 100%;
                    border-collapse: collapse;
                    margin-bottom: 30px;
                }
                th, td {
                    border: 1px solid #ddd;
                    padding: 10px;
                    text-align: center;
                }
                th {
                    background-color: #f2f2f2;
                    font-weight: bold;
                }
                .period-time {
                    font-size: 0.8em;
                    color: #666;
                    display: block;
                }
                .course {
                    font-weight: bold;
                    color: #333;
                }
                .teacher {
                    font-size: 0.85em;
                    color: #666;
                }
                .stats {
                    margin-top: 40px;
                    padding: 15px;
                    background-color: #f9f9f9;
                    border-radius: 5px;
                }
                .footer {
                    margin-top: 30px;
                    text-align: center;
                    font-size: 0.8em;
                    color: #666;
                }
                .lab {
                    background-color: #e6f7ff;
                    border-left: 2px solid #0099cc;
                    border-right: 2px solid #0099cc;
                }
                .lab-start {
                    border-top: 2px solid #0099cc;
                    border-left: 2px solid #0099cc;
                    border-right: 2px solid #0099cc;
                }
                .lab-end {
                    border-bottom: 2px solid #0099cc;
                    border-left: 2px solid #0099cc;
                    border-right: 2px solid #0099cc;
                }
                .admin {
                    background-color: #fff2e6;
                }
                .theory {
                    background-color: #f2f2f2;
                }
                .free {
                    background-color: #f9f9f9;
                    color: #999;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Class Timetable</h1>
        """
        
        # Add generation timestamp
        html_content += f"""
                <p style="text-align: center;">Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        """
        
        # Add timetables for each section
        for s in self.sections:
            html_content += f"""
                <h2>Section {s} Timetable</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Day</th>
            """
            
            # Add period headers
            for p in range(1, 8):
                html_content += f"""
                            <th>Period {p}<span class="period-time">{self.periods[p-1]["time"]}</span></th>
                """
            
            html_content += """
                        </tr>
                    </thead>
                    <tbody>
            """
            
            # Add rows for each day
            for d in self.days:
                html_content += f"""
                        <tr>
                            <td>{d}</td>
                """
                
                for p in range(1, 8):
                    if p in self.solution[s][d]:
                        course = self.solution[s][d][p]["course"]
                        teacher = self.solution[s][d][p]["teacher"]
                        
                        # Determine cell class based on course type
                        cell_class = ""
                        if course == "FREE":
                            cell_class = "free"
                            html_content += f"""
                            <td class="{cell_class}">
                                <div class="course">FREE</div>
                            </td>
                            """
                        elif course in ['PD', 'LIB', 'ACT']:
                            cell_class = "admin"
                            html_content += f"""
                            <td class="{cell_class}">
                                <div class="course">{course}</div>
                                <div class="teacher">{teacher}</div>
                            </td>
                            """
                        elif any(lab in course for lab in ['LAB']):
                            # Check if this is part of a lab session
                            if p == 4 or p == 6:  # Start of lab session
                                cell_class = "lab lab-start"
                            elif p == 5 or p == 7:  # End of lab session
                                cell_class = "lab lab-end"
                            else:
                                cell_class = "lab"
                            
                            html_content += f"""
                            <td class="{cell_class}">
                                <div class="course">{course}</div>
                                <div class="teacher">{teacher}</div>
                            </td>
                            """
                        else:
                            cell_class = "theory"
                            html_content += f"""
                            <td class="{cell_class}">
                                <div class="course">{course}</div>
                                <div class="teacher">{teacher}</div>
                            </td>
                            """
                    else:
                        html_content += """
                            <td class="free">
                                <div class="course">FREE</div>
                            </td>
                        """
                
                html_content += """
                        </tr>
                """
            
            html_content += """
                    </tbody>
                </table>
            """
        
        # Add statistics
        html_content += """
                <div class="stats">
                    <h2>Timetable Statistics</h2>
        """
        
        # Subject distribution
        for s in self.sections:
            html_content += f"""
                    <h3>Section {s} Subject Distribution</h3>
                    <table>
                        <thead>
                            <tr>
                                <th>Subject</th>
                                <th>Allocated Periods</th>
                                <th>Required Periods</th>
                            </tr>
                        </thead>
                        <tbody>
            """
            
            subject_counts = {}
            for d in self.days:
                for p in range(1, 8):
                    if p in self.solution[s][d]:
                        course = self.solution[s][d][p]["course"]
                        subject_counts[course] = subject_counts.get(course, 0) + 1
            
            for subject, count in sorted(subject_counts.items()):
                required = self.courses[subject][0]
                html_content += f"""
                            <tr>
                                <td>{subject}</td>
                                <td>{count}</td>
                                <td>{required}</td>
                            </tr>
                """
            
            html_content += """
                        </tbody>
                    </table>
            """
        
        # Teacher workload
        html_content += """
                    <h3>Teacher Workload</h3>
                    <table>
                        <thead>
                            <tr>
                                <th>Teacher</th>
                                <th>Total Periods</th>
                            </tr>
                        </thead>
                        <tbody>
        """
        
        teacher_workload = {}
        for s in self.sections:
            for d in self.days:
                for p in range(1, 8):
                    if p in self.solution[s][d]:
                        teacher = self.solution[s][d][p]["teacher"]
                        teacher_workload[teacher] = teacher_workload.get(teacher, 0) + 1
        
        for teacher, count in sorted(teacher_workload.items()):
            html_content += f"""
                            <tr>
                                <td>{teacher}</td>
                                <td>{count}</td>
                            </tr>
            """
        
        html_content += """
                        </tbody>
                    </table>
                </div>
        """
        
        # Close HTML
        html_content += """
                <div class="footer">
                    Generated using Timetable Generator
                </div>
            </div>
        </body>
        </html>
        """
        
        # Write to file
        try:
            with open(output_file, 'w') as f:
                f.write(html_content)
            print(f"Timetable HTML saved to {output_file}")
            return True
        except Exception as e:
            print(f"Error saving HTML: {e}")
            return False
    
    def run(self):
        print("Starting timetable generation process...")
        self.generate_variables()
        print("Variables generated successfully")
        
        self.add_constraints()
        print("Constraints added successfully")
        
        print("Attempting to solve...")
        success = self.solve()
        
        if success:
            print("Solution found! Generating output...")
            self.print_timetable()
            self.generate_html()
            return True
        else:
            print("Failed to find a solution")
            return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate a school timetable.')
    parser.add_argument('--free-periods', action='store_true', 
                        help='Include free periods in the timetable')
    args = parser.parse_args()
    
    generator = TimetableGenerator(include_free_periods=args.free_periods)
    generator.run()