Here are the commands to run the final timetable generator:

To generate a timetable with free periods (recommended, as it's more likely to find a solution):
cd /home/moni/Desktop/ScheduleEngine && python3 final_timetable_generator.py --free-periods
To generate a timetable without free periods (more constrained, might be harder to find a solution):
cd /home/moni/Desktop/ScheduleEngine && python3 final_timetable_generator.py
To view the generated HTML timetable (after running one of the above commands):
xdg-open /home/moni/Desktop/ScheduleEngine/timetable.html
The first command is the most reliable option as it includes free periods, making the problem more flexible and easier to solve. After running it, the timetable will be displayed in the console and saved as an HTML file that you can open in any web browser.