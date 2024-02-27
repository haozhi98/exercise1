## How to run
I am using `python3.10.13`, any python `version~3.10` should be compatible\
`pip install -r requirements`
### To execute client program
Ensure server is already running\
`python simple_rest_server.py`

For async approach\
`python simple_client.py async`

For multi-threading approach\
`python simple_client.py threading`

### Analyse Results
Run analysis scripts which adds the summarised log data to the `throughputs.txt` file\
`python analyse_log.py`

Sample output in `throughputs.txt`

Average Requests Rate: 165.85416666666666\
Max Possible Throughput: 100\
Average Throughput: 82.66666666666667\
Lowest Throughput: 69\
Average Ignored from Queue: 0.0\
Average Limited by Limiter: 0.0\
Exceeds: 11\
Bans: 0\
Nonce Errors: 701\
Total Time: 0:00:49.938000

## Task
### Your task is to review and modify the client code to maximize the throughput available to the client
We’d like to hear about the issues you found in the existing code, what design choices you used (e.g why you might use asynchronous code instead of multithreading)
and how you determined the impact your design had on speed. You may face some decisions where there is no clear “best” choice - 
There is no magic answer, each approach will have tradeoffs.

## The approach
1. Find a way to calculate throughput and theoretical optimal throughput
2. The issue is that requests are created at a random rate which could be higher than the max request rate (20/s)
3. Two ways in which orders expire before sending, when received from queue, and while waiting in acquire
4. Ensure we do not exceed the limit rate as it may result in ban

## Metrics (units / second)
### Max Possible Throughput
The number of orders received from the queue, including orders that expire before processing and during processing (capped at 20*5 API_KEY = 100 orders per second)
### Average Throughput
The number of orders that were successfully made
### Ignored from queue
Number of orders that expired before waiting for acquire due to timeout of 1 second between order creation and order processing`
### Limited by Limiter
Number of orders that expire while waiting for acquire
### Exceeds
Number of rate limit errors
- Since the number of limit exceeds accumulate without reset, we need to keep it to 0, although in a real world system, this metric probably resets on a regular time basis

### Initial test
From the calculation of throughput, we have about a rate of ~`75` in total for 5 keys with a max possible throughput of ~`90`, so about `15` requests per second out of a possible `18`
No request rate overflow at all
Average ignored from queue was ~`8.7` and limited by limiter was ~`6.3`
Thus overhead was high as quite a few requests expired even before being removed from the queue

### Assumption / Question 1
While we are trying to optimize throughput only, how much priority do we give to time between order creation or order sent?
(quality of order: larger movement in price the longer it takes between creation and sending of orders -> lower margins on trade)

If we forgo the limit of 1 sec between order creation and order sending, we can increase the throughput, although we might not want that

### ISSUES: 1
There is some overhead in each call such that in acquire, which adds to the time between orders
Thus, when we have n time between calls, where n = 1 sec / max_calls_per_sec, instead we have n + x time, where x is the overhead
so now we are limiting our throughput to: throughput = 1 / (n + x)

### IDEA 1: Increase current time in acquire -> offset overhead of time between orders -> set less time between orders -> higher throughput
- Add offset to current_time -> Reduce wait time between sequential requests and per_sec_rate requests
- Need to add same offset to timeout_ms -> current_time is used to measure order expiry
- Need to minus same offset from _last_request_time and _request_times[i] -> we want to keep the offset only to current_time, but not to _last_request_time and _request_times[i] (offset will cancel out)
    - Just minus from _last_request_time and _request_times[i]
- What offset to use? Calculating offset

### Optimal Throughput given that we cannot exceed max_request_per_sec
- With the current approach of adding an offset in _last_request_time and _request_times[i] to reduce wait time between requests and requests/sec, we reduce requests that expire while waiting to acquire
- With less waiting, overall acquiring time is also lower -> fewer requests will expire while waiting in the queue
- Offset of 25ms:
    - In first 10,000 orders -> Achieved throughput: `81.2`
    - 29 Exceeds of request limit (too high)
    - In the first 20,000 orders, throughput dropped to `74.3`
    - 43 Exceeds and 1505 rejections due to blocked key

- Offset = `10` ms
    - Achieved throughput: `78.7`
    - 4 Exceeds of request limit in ~30,000 requests
    - Improved throughput of ~`3.7` orders / second, while only having ~`1/10,000` requests that exceed order limit

### IDEA 2: Optimising sleep time when waiting between requests and requests / min
Using tests of ~`30,000`
- Increasing sleep_time to 0.002
    - Lower overhead due to less switching by the asyncio library
    - Longer time between when order is ready to send but still waiting in acquire
    - Throughput: `78.7`, Exceeds: `3`
    - Almost identical results to original value of 0.001
- Decreasing sleep_time to 0.005 -> higher overhead -> more requests expired in queue, no difference in throughput of acquire
    - Throughput: `80.7`, Exceeds: `20`
    - Improved throughput, but number of exceeds is unsustainable
- Current rate of 0.001 is quite desirable

## Multithreading
To balance order creation and order execution, the thread controller is an async function with the async request generator, each being allocated the same amount of time on average
- In request generator: `async.io.sleep(MAX_SLEEP_MS = 1000 / PER_SEC_RATE / len(VALID_API_KEYS) * 1.05 * 2.0)` `sleep_ms = random.randint(0, MAX_SLEEP_MS)`
- In thread controller: `async_sleep_time = (1 / PER_SEC_RATE) * 1.05`

To maximise throughput without going over the order limit, the program created as many threads as the max number of requests allowed / second, while restricting the `time_to_live` for each order.
- `time_to_live` time is recorded when order is removed from the queue by the thread controller, and the order is passed into the thread if `time_to_live` > 0
- In the thread, we enforce that the thread will not give itself up for the duration of `1` second, calling sleep on the remaining time
    - `time.sleep(1 - (current_time - entry_time)`
    - Thus with 20 threads per API_KEY, and each threading running for `1` second, we achieve the limit of 20 calls / second

### Advantages
Throughput rate is high since the overhead for ensuring adherence to order limit is keep by setting the max number of threads and ensuring each thread takes 1 second per request
- `87.8` successful request/sec
- `0` exceeds: There are no instances of order limit exceed due to the limit set by the number of threads and time taken by each thread
- `43` Nonce Errors: Since nonces must be strictly increasing for each API_KEY, due to the nature of multi-threading where the order of thread execution is not fixed, there are a few instances where threads with newer orders are executed before older orders. At a rate of about ~`1/1000` requests, it is not a significant issue

### Disadvantages
Hard to ensure fair allocation of CPU time to order generator and thread controller in the case where there might be a lot more or less orders being created (perhaps due to the nature of the simulation)
In our stress test, where the order creation rate is doubled, we see that the thread execution order had a lot more disorder, likely due to the higher rate of switching between the async functions.
Might need to introduce thread synchronization in such cases, which would increase the complexity of the implementation and introduce more overhead
In the stress test, there were also `11` exceeds in about `5000` requests, indicating that the order limit mechanism did not perform well when throughput was at its limit, likely due to variance. The solution will be to introduce a buffer such that the order limit is not reached even where there is variance in the timing mechanism and context switching of theads.


## Possible Improvements
Python Global Interpreter Lock prevents true parallelism with multithreading since it essentially limits the program to a single point of execution. Overall, I would say this could be ideal in this program, which is largely I/O-bound.
With a multi-processing approach, we can acheive true parallelism, but we will need more resources, process synchronization which would complicate the program. Furthermore, the async and multi-threading approach have almost reached optimal throughput so there is not much incentive to try a multi-processing approach. 

Perhaps if we have higher request limit rates, or more APIs, it would make sense to run multi-processing. Another alternative would be to run 1 process for each API, and a separate process for order generation. With such an approach, the main concern would be synchronizing between the difference processes when they acquire the orders, such that a single order is not sent more than once or an order processed before another.
