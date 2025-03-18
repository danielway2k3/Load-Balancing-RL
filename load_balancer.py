#!/usr/bin/env python3

import argparse
from control import SDNController

def main():
    parser = argparse.ArgumentParser(description='DQN-based SDN Load Balancer with Ryu')
    parser.add_argument('--mode', choices=['train', 'run'], required=True,
                        help='Train the model or run with existing model')
    parser.add_argument('--episodes', type=int, default=30,
                        help='Number of episodes for training (default: 30)')
    parser.add_argument('--model', type=str, default='dqn_load_balancer.pth',
                        help='Path to the model file for loading/saving')
    
    args = parser.parse_args()
    
    controller = SDNController()
    
    if args.mode == 'train':
        print(f"Starting training with {args.episodes} episodes...")
        controller.train(episodes=args.episodes)
    elif args.mode == 'run':
        print(f"Running load balancer with model from {args.model}...")
        controller.run(model_path=args.model)

if __name__ == "__main__":
    main()