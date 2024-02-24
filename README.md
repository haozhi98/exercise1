### Initial test
From the calculation of throughput, we have about a rate of `76.5` in total for 5 keys, so about `15.3` requests per second out of a possible `20`
No request rate overflow at all


### Assumption / Question 1
While we are trying to optimize throughput only, how much priority do we give to time between order creation or order sent?
(quality of order: larger movement in price the longer it takes between creation and sending of orders -> lower margins on trade)

If we forgo the limit of 1 sec between order creation and order sending, we can increase the throughput, although we might not want that

### ISSUES: 1
There is some overhead in each call such that in acquire, which adds to the time between orders
Thus, when we have n time between calls, where n = 1 sec / max_calls_per_sec, instead we have n + x time, where x is the overhead
so now we are limiting our throughput to: throughput = 1 / (n + x)

### IDEA 1:: Increase current time in acquire -> offset overhead of time between orders -> set less time between orders -> higher throughput
- Add offset to current_time -> Reduce wait time between sequential requests and per_sec_rate requests
- Need to add same offset to timeout_ms -> current_time is used to measure order expiry
- Need to minus same offset from _last_request_time and _request_times[i] -> we want to keep the offset only to current_time, but not to _last_request_time and _request_times[i] (offset will cancel out)
    - Just minus from _last_request_time and _request_times[i]
- What offset to use? Calculating offset
1. Measure theoretical optimal throughput
    requests < 100 -> throughput = requests
    requests >= 100 -> throughput = 100

### Optimal Throughput given that we cannot exceed max_request_per_sec
- With current approach of adding an offset in _last_request_time and _request_times[i] to reduce wait time between requests and requests/sec, we reduce requests that expire while waiting to acquire to ~0.16 / sec
- With less waiting, overall acquiring time is also lower -> fewer requests will expire while waiting in the queue
- Current throughput: `82.7`
    - 15 Exceeds of request limit
- Max possible throughput: `88-89`

### Optimising sleep time when waiting between requests and requests / min
- Increasing sleep_time to 0.002 -> lower overhead -> marginal / detrimental as increased number of requests expired in queue -> lower throughput of acquire
- Decreasing sleep_time to 0.005 -> higher overhead -> more requests expired in queue, no difference in throughput of acquire
    
### IDEA 2: Increase remaining_ttl -> More requests are processed past 1 sec of creation
-> Also increases timeout in acquire -> Less likely to timeout in limiter

### IDEA 3: Change the sleep time in acquire
lower sleep time -> less time between (a) actual time we can make a request (according to rate limit) and (b) time when granted access
higher sleep time -> less overhead since the async process is sleeping for longer
    
throughput is maxed at about 83, which could be the max already given the request rate

## Metrics
### Ignored from queue
Time between order and processing
Maybe if the time remaining is too little, do not pass to Limiter since its unlikely to process

### Limited by Limiter
Time between order and request
### Exceeds
Since the number of limit exceeds accumulate without reset, might need to keep it to 0, IRL: probably resets

## Task
### Your task is to review and modify the client code to maximize the throughput available to the client
1. Find a way to calculate throughput
should measure theoretical optimal throughput
requests < 100 -> throughput = requests
requests >= 100 -> throughput = 100
2. The issue is that requests are created at a random rate which could be higher than the max request rate (20/s)
We’d like to hear about the issues you found in the existing code, what design choices you used (e.g why you might use asynchronous code instead of multithreading)
and how you determined the impact your design had on speed. You may face some decisions where there is no clear “best” choice - 
There is no magic answer, each approach will have tradeoffs.
