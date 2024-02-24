import datetime as dt
from datetime import datetime

with open('async-debug.log') as file:
    lines = file.readlines()

startTime = None
one_second = dt.timedelta(seconds=1)
time_format = '%H:%M:%S,%f'

metrics = []
throughput = 0
ignored_queue = 0
limited = 0
bans = 0
exceeds = 0

item = lines[0].split()
firstTime = startTime = datetime.strptime(item[1], time_format)
requests = []

for line in lines[1:]:
    items = line.split()
    time_obj = datetime.strptime(items[1], time_format)

    if time_obj - startTime >= one_second:
        metrics.append((throughput, ignored_queue, limited))
        throughput = 0
        ignored_queue = 0
        limited = 0
        startTime = time_obj
    elif items[5] == 'INFO':
        if items[10] == '200,':
            throughput += 1
        elif items[7] == 'Requests':
            requests.append(int(items[8]))
    elif items[5] == 'WARNING':
        if items[11] == 'queue':
            ignored_queue += 1
        elif items[11] == 'limiter':
            limited += 1
        elif items[10] == '429,':
            exceeds += 1
        # elif items[10] == '403,':
        #     bans += 1

transposed_metrics = list(zip(*metrics))

avg_max_throughput = sum(requests) / len(requests)
avg_throughput = sum(transposed_metrics[0]) / len(transposed_metrics[0])
avg_ignored_queue = sum(transposed_metrics[1]) / len(transposed_metrics[1])
avg_limited = sum(transposed_metrics[2]) / len(transposed_metrics[2])
min_throughput = min(metrics, key=lambda x: x[0])[0]

totalTime = time_obj - firstTime

with open('throughputs.txt', 'a') as file:
    file.write(f"\nMax Possible Throughput: {avg_max_throughput}\n")
    file.write(f"Average Throughput: {avg_throughput}\n")
    file.write(f"Lowest Throughput: {min_throughput}\n")
    file.write(f"Average Ignored from Queue: {avg_ignored_queue}\n")
    file.write(f"Average Limited by Limiter: {avg_limited}\n")
    file.write(f"Exceeds: {exceeds}\n")
    file.write(f"Total Time: {totalTime}\n")