# Initial test
From the calculation of throughput, we have about a rate of 75-80 in total for 5 keys, so about 15-16 requests per second out of a possible 20
No request rate overflow at all


Assumption / Question 1
While we are trying to optimize throughput only, how much priority do we give to time between order creation or order sent?
(quality of order: larger movement in price the longer it takes between creation and sending of orders -> lower margins on trade)

If we forgo the limit of 1 sec between order creation and order sending, we can increase the throughput, although we might not want that

ISSUES: 1
There is some overhead in each call such that in acquire, which adds to the time between orders
Thus, when we have n time between calls, where n = 1 sec / max_calls_per_sec, instead we have n + x time, where x is the overhead
so now we are limiting our throughput to: throughput = 1 / (n + x)

    
IDEA 1: Increase remaining_ttl -> More requests are processed past 1 sec of creation
-> Also increases timeout in acquire -> Less likely to timeout in limiter
    
IDEA 2:: Increase current time in acquire -> more "time" between requests -> higher rate
larger offset -> more likely to timeout

IDEA 3: Change the sleep time in acquire
lower sleep time -> less time between (a) actual time we can make a request (according to rate limit) and (b) time when granted access
higher sleep time -> less overhead since the async process is sleeping for longer
    
throughput is maxed at about 83, which could be the max already given the request rate
Metrics
- Ignored from queue -> Time between order and processing
    - Maybe if the time remaining is too little, do not pass to Limiter since its unlikely to process
- Limited by Limiter -> Time between order and request
- Exceeds -> Since the number of limit exceeds accumulate without reset, might need to keep it to 0, IRL: probably resets
    

Your task is to review and modify the client code to maximize the throughput available to the client
1. Find a way to calculate throughput
should measure theoretical optimal throughput
requests < 100 -> throughput = requests
requests >= 100 -> throughput = 100
2. The issue is that requests are created at a random rate which could be higher than the max request rate (20/s)
We’d like to hear about the issues you found in the existing code, what design choices you used (e.g why you might use asynchronous code instead of multithreading)
and how you determined the impact your design had on speed. You may face some decisions where there is no clear “best” choice - 
There is no magic answer, each approach will have tradeoffs.
