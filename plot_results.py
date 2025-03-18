import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import os

def plot_training_results(csv_file='monitoring_data.csv'):
    """Plot the results from the monitoring data"""
    # Load data
    df = pd.read_csv(csv_file)
    
    # Convert timestamp to datetime
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
    
    # Create a figure with subplots
    fig, axes = plt.subplots(3, 1, figsize=(12, 18))
    
    # Plot latency over time
    sns.lineplot(data=df, x='timestamp', y='latency', hue='host', ax=axes[0])
    axes[0].set_title('Latency over Time')
    axes[0].set_ylabel('Latency (ms)')
    
    # Plot throughput over time
    sns.lineplot(data=df, x='timestamp', y='throughput', hue='host', ax=axes[1])
    axes[1].set_title('Throughput over Time')
    axes[1].set_ylabel('Throughput (Mbps)')
    
    # Plot CPU usage over time
    sns.lineplot(data=df, x='timestamp', y='cpu', hue='host', ax=axes[2])
    axes[2].set_title('CPU Usage over Time')
    axes[2].set_ylabel('CPU Usage (%)')
    
    # Adjust layout
    plt.tight_layout()
    plt.savefig('./images/training_results.png')
    plt.show()

def plot_reward_progression(reward_file='rewards.csv'):
    """Plot the progression of rewards during training"""
    try:
        df = pd.read_csv(reward_file)
        
        plt.figure(figsize=(10, 6))
        sns.lineplot(data=df, x='episode', y='reward')
        plt.title('Reward Progression During Training')
        plt.xlabel('Episode')
        plt.ylabel('Reward')
        plt.grid(True)
        plt.savefig('./images/reward_progression.png')
        plt.show()
        
    except Exception as e:
        print(f"Error plotting rewards: {e}")

if __name__ == "__main__":
    os.makedirs('./images', exist_ok=True)
    plot_training_results()
    plot_reward_progression()