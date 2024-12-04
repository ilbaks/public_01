#%% Step_1: Read data
import pandas as pd
from itertools import product
from mip import Model, xsum, maximize, BINARY

# Read data
df = pd.read_csv('./data/df_result_full.csv')
NUM = 40_000
df_sample = df.iloc[:NUM, :].copy()
df_sample['customer_rk_sb8'] = df_sample['customer_rk_sb8'].round().astype(int)

#%% Step 2 v3
#=====================================================
# Define time horizon and action limits
import time
# Start the timer
start_time = time.time()



time_horizon = 1

days = range(time_horizon)
max_actions = NUM

# Define the maximum number of actions per channel
limit_channel_per_day = {
    "call": NUM * 0.4,
    "email": NUM * 0.2,
    "push": NUM * 0.3,
    "sms": NUM * 0.25,
}

customers = list(map(int, list(df_sample['customer_rk_sb8'].unique())))

# # Define products and channels dynamically based on your DataFrame
products_channels = [
    ("cash", "call"), ("cash", "email"), ("cash", "push"), ("cash", "sms"),
    ("cc", "call"), ("cc", "email"), ("cc", "push"), ("cc", "sms"),
    ("dc", "push"), ("dc", "sms"),
    ("dep", "push"), ("dep", "sms")
]

# Prepare the dictionary of probabilities dynamically
dict_C = {
    (int(row['customer_rk_sb8']), product, channel): 1_000 * float(row[f'prob_{product}_{channel}'])
    for _, row in df_sample.iterrows()
    for product, channel in products_channels
    if f'prob_{product}_{channel}' in df_sample.columns
}

# Optimization model setup
model = Model()
model.clear()
model.clique = 2
model.max_mip_gap = 0.01
model.cuts = 0

# Decision variables
x = {
    (customer, product, channel, day): model.add_var(var_type=BINARY)
    for customer in customers
    for product, channel in products_channels
    for day in days
}

# Objective function
model.objective = maximize(xsum(
    dict_C.get((customer, product, channel), 0) * x[(customer, product, channel, day)]
    for customer in customers
    for product, channel in products_channels
    for day in days
))

# Constraints
# Constraint 1: at most one action per customer per day
for customer in customers:
    for day in days:
        model += xsum(
            x[(customer, product, channel, day)] for product, channel in products_channels
        ) <= 1  

# Global action limit
model += xsum(x.values()) <= max_actions

# Constraint: Limit actions per channel per day
for channel in limit_channel_per_day:
    for day in days:
        model += xsum(
            x[(customer, product, channel, day)]
            for customer in customers
            for product, _channel in products_channels
            if _channel == channel
        ) <= limit_channel_per_day[channel]


# Constraint : Ensure at least 60% of credit-related actions are in the "call" channel
credit_products = ["cash", "cc", "dc", "dep"]
model += xsum(
    x.get((customer, product, "call", day), 0)
    for customer in customers
    for product in credit_products
    for day in days
) >= 0.6 * xsum(
    x.get((customer, product, channel, day), 0)
    for customer in customers
    for product in credit_products
    for channel in ["call", "email", "push", "sms"]
    for day in days
)


# Define the minimum number of days between contacts for each channel-channel combination
min_days_between = {
    ("call", "call"): 3,
    ("call", "sms"): 2,
    ("call", "push"): 1,
    ("call", "email"): 1,

    ("sms", "call"): 3,
    ("sms", "sms"): 2,
    ("sms", "push"): 1,
    ("sms", "email"): 1,

    ("push", "call"): 3,
    ("push", "sms"): 2,
    ("push", "push"): 1,
    ("push", "email"): 1,

    ("email", "call"): 3,
    ("email", "sms"): 2,
    ("email", "push"): 1,
    ("email", "email"): 1,

}

# Add constraints for the contact policy
for customer in customers:
    for product1, channel1 in products_channels:
        for day in days:
            for product2, channel2 in products_channels:
                if (channel1, channel2) in min_days_between:
                    gap = min_days_between[(channel1, channel2)]
                    for offset in range(1, gap):
                        if day + offset < time_horizon:
                            model += (
                                x[(customer, product1, channel1, day)]
                                + x.get((customer, product2, channel2, day + offset), 0)
                            ) <= 1


# Solve the model with a time limit (optional)
model.optimize(max_seconds=600)
Configure the solver for less relaxation reliance
model.optimizer.set_int_param("heuristics", 1)  # Enable heuristics

model.optimize(relax=False)

# Extract and save results
if model.num_solutions:
    selected_actions = [
        (customer, product, channel, day)
        for customer in customers
        for product, channel in products_channels
        for day in days
        if x[(customer, product, channel, day)].x >= 0.98
    ]
    print("Selected actions:", selected_actions)
    # with open("selected_actions.json", "w") as f:
    #     json.dump(selected_actions, f)
    # print("Selected actions saved to 'selected_actions.json'")
else:
    print("No solution found.")


# Stop the timer
end_time = time.time()

# Calculate execution time in seconds and minutes
execution_time_seconds = end_time - start_time
execution_time_minutes = execution_time_seconds / 60

# Print execution time in minutes
print(f"Execution Time: {execution_time_seconds:.2f} seconds ({execution_time_minutes:.2f} minutes)")
