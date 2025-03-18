import numpy as np
import random
import torch
import torch.nn as nn
import torch.optim as optim
from collections import deque
import torch.nn.functional as F

class DQNNetwork(nn.Module):
    def __init__(self, state_size=9, action_size=3):
        super(DQNNetwork, self).__init__()
        self.fc1 = nn.Linear(state_size, 24)
        self.fc2 = nn.Linear(24, 24)
        self.fc3 = nn.Linear(24, action_size)
        
    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        return self.fc3(x)

class DQNAgent:
    def __init__(self, state_size=9, action_size=3):
        self.state_size = state_size
        self.action_size = action_size
        
        # Hyperparameters
        self.memory = deque(maxlen=2000)
        self.gamma = 0.95    # discount factor
        self.epsilon = 1.0   # exploration rate
        self.epsilon_min = 0.01
        self.epsilon_decay = 0.995
        self.learning_rate = 0.001
        
        # Create two networks
        self.model = DQNNetwork(state_size, action_size)
        self.target_model = DQNNetwork(state_size, action_size)
        self.optimizer = optim.Adam(self.model.parameters(), lr=self.learning_rate)
        
        # Initialize target network with model weights
        self.update_target_model()
        
    def update_target_model(self):
        self.target_model.load_state_dict(self.model.state_dict())

    def remember(self, state, action, reward, next_state, done):
        self.memory.append((state, action, reward, next_state, done))

    def act(self, state):
        if np.random.rand() <= self.epsilon:
            return random.randrange(self.action_size)
        
        state_tensor = torch.FloatTensor(state).unsqueeze(0)
        self.model.eval()
        with torch.no_grad():
            action_values = self.model(state_tensor)
        self.model.train()
        
        return torch.argmax(action_values).item()

    def replay(self, batch_size=32):
        if len(self.memory) < batch_size:
            return
        
        minibatch = random.sample(self.memory, batch_size)
        for state, action, reward, next_state, done in minibatch:
            state_tensor = torch.FloatTensor(state).unsqueeze(0)
            next_state_tensor = torch.FloatTensor(next_state).unsqueeze(0)
            
            target = reward
            if not done:
                with torch.no_grad():
                    target = reward + self.gamma * torch.max(self.target_model(next_state_tensor))
            
            # Get current Q values
            self.model.eval()
            with torch.no_grad():
                current_q = self.model(state_tensor)
            self.model.train()
            
            # Update Q value for selected action
            target_f = current_q.clone().detach()
            target_f[0][action] = target
            
            # Train the model
            self.optimizer.zero_grad()
            outputs = self.model(state_tensor)
            loss = F.mse_loss(outputs, target_f)
            loss.backward()
            self.optimizer.step()
            
        # Decay epsilon
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay

    def load(self, name):
        self.model.load_state_dict(torch.load(name))

    def save(self, name):
        torch.save(self.model.state_dict(), name)

    def preprocess_state(self, metrics):
        """Convert raw metrics to state vector for DQN"""
        state = []
        for host in ['h1', 'h2', 'h3']:
            state.append(metrics[host]['latency'])
            state.append(metrics[host]['throughput'])
            state.append(metrics[host]['cpu'])
        return np.array(state)

    def calculate_reward(self, host, metrics):
        """Calculate reward based on throughput, latency and CPU usage"""
        throughput = metrics[host]['throughput']
        latency = metrics[host]['latency']
        cpu = metrics[host]['cpu']
        
        # Reward formula: throughput - 0.05 * latency - 0.1 * cpu
        reward = throughput - 0.05 * latency - 0.1 * cpu
        return reward