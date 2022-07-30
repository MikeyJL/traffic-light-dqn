"""Instantiates SUMO with pre-defined network and configuration for DQN."""

import os
import sys
from argparse import ArgumentParser

import traci
from sumolib import checkBinary
from torch.utils.tensorboard.writer import SummaryWriter

from agent import Agent
from _typings import TrafficLightSystem, Experience

# CLI parser
parser = ArgumentParser(description="CLI for SUMO RL")
parser.add_argument(
    "-e",
    "--episodes",
    metavar="\b",
    type=int,
    help="The number of episodes to run.",
    default=10,
)
parser.add_argument(
    "-m",
    "--max_step",
    metavar="\b",
    type=int,
    help="The maximum number of steps in each episode.",
    default=3600,
)
parser.add_argument(
    "-g",
    "--gui",
    action="store_true",
    help="Sets SUMO to launch with GUI.",
)
args = parser.parse_args()

print("\n========== Starting Simulation ==========")
print(f"Mode: {'GUI' if args.gui else 'No GUI'}")
print(f"Number of episodes: {args.episodes}")
print(f"Maximum of steps: {args.max_step}\n")

# Checks for SUMO_HOME enviroment
if "SUMO_HOME" in os.environ:
    tools = os.path.join(os.environ["SUMO_HOME"], "tools")
    sys.path.append(tools)
else:
    sys.exit("please declare environment variable 'SUMO_HOME'")

# Setup
sumoBinary = checkBinary("sumo-gui" if args.gui else "sumo")
sumoCmd = [sumoBinary, "-W", "-c", "data/train-network/osm.sumocfg"]

traci.start(sumoCmd)

# Create a new starting state file if not existing
START_STATE_PATH = "data/train-network/start.state.xml"
if not os.path.exists(START_STATE_PATH):
    traci.simulation.saveState(START_STATE_PATH)

# All TLS agents
TLS_AGENTS: tuple[Agent, ...] = tuple(
    Agent(
        TrafficLightSystem(
            tls_id,
            traci.trafficlight.getControlledLanes(tls_id),
            traci.trafficlight.getAllProgramLogics(tls_id)[0].phases,
        )
    )
    for tls_id in traci.trafficlight.getIDList()
)

# Tensorboard logger
writter = SummaryWriter()

# Main simulation loop
for ep in range(args.episodes):
    EPS_REWARD: float = 0

    # Episode simulation stepper
    for step in range(args.max_step):

        # Prepares action for each TLS agent
        sa_pairs = [agent.prepare_step(step) for agent in TLS_AGENTS]

        traci.simulationStep()

        # In the next step, evaluate the action taken
        for idx, agent in enumerate(TLS_AGENTS):
            state, action = sa_pairs[idx]
            next_state, reward = agent.evaluate_step(state)

            # Saves the experience
            agent.memory.push(Experience(state, action, next_state, reward))

            # Performs training with epsilon greedy
            agent.train(step)

            # Updates this episode's reward
            EPS_REWARD += reward.reshape(-1)[0].item()

    # Saves data to tensorboard
    writter.add_scalar("Episode reward", EPS_REWARD, ep)

    # Resets simulation after each episode
    traci.simulation.loadState(START_STATE_PATH)


writter.close()
traci.close()
