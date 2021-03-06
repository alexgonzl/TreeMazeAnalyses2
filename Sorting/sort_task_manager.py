import sys
import getopt
import json
import time
import warnings
import traceback
from pathlib import Path
from sort_functions import sort_main

warnings.simplefilter(action='ignore', category=FutureWarning)

if __name__ == '__main__':
    # Store taskID and TaskFile
    task_num = -1
    task_num_str = ''
    sorter = 'KS2'
    subject_id = ''
    data_dir = ''
    overwrite_flag = False

    TasksDir = Path.cwd() / 'TasksDir'
    if not TasksDir.exists():
        sys.exit('Task directory not found.')

    if len(sys.argv) < 3:
        print("Usage: %s -t task# -s sorter -a 'animal id' -o" % sys.argv[0])
        print("Example: %s -t 1 -s KS2 -a Li" % sys.argv[0])
        sys.exit('Invalid input.')

    myopts, args = getopt.getopt(sys.argv[1:], "t:a:s:d:o")
    for opt, attr in myopts:
        if opt == '-t':
            task_num = int(attr)
            task_num_str = str(attr)
        elif opt == '-s':
            sorter = str(attr)
        elif opt == '-a':
            subject_id = str(attr)
        elif opt == '-d':
            data_dir = Path(attr)
        elif opt == '-o':
            overwrite_flag = True
        else:
            print("Usage: %s -t taskID -a animal id" % sys.argv[0])
            sys.exit('Invalid input. Aborting.')

    print('Sort Manager: task {}, id {}, data {}'.format(task_num_str, subject_id, str(data_dir)))
    task_table_dir = data_dir / subject_id / 'TasksDir'
    if not task_table_dir.exists():
        sys.exit('Task directory not found.')

    task_table_filepath = task_table_dir / ('sort_{}_{}.json'.format(subject_id, sorter))
    try:
        if task_table_filepath.exists():
            with task_table_filepath.open(mode='r') as f:
                task_table = json.load(f)
        else:
            sys.exit('Could not get Task Table. Aborting.')
    except:
        sys.exit('Could not get Task Table. Aborting.')

    if task_num >= 0:
        subtask_info = task_table[task_num_str]
        session_name = subtask_info['session_name']
        n_files = subtask_info['n_files']
        subtask_list = subtask_info['files']
        print("Processing Session {}".format(session_name))

        for subtask_id, subtask in subtask_list.items():
            try:
                print("Sorting Tetrode # {}".format(subtask['tt_id']))
                t1 = time.time()
                sort_main(subtask, overwrite_flag)
                t2 = time.time()
                print("Task Completed. Total Task Time {0:0.2f}s".format(t2 - t1))
            except KeyboardInterrupt:
                print('Keyboard Interrupt Detected. Aborting Task Processing.')
                sys.exit()
            except:
                print("Error", sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2].tb_lineno)
                print("Unable to process task {} of {}".format(subtask['tt_id'], session_name))
                traceback.print_exc(file=sys.stdout)
    else:
        sys.exit('Invalid task number.')
