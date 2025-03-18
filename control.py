import requests
import time
import json
import numpy as np
from monitoring import Monitor
from dqn_agent import DQNAgent

class SDNController:
    def __init__(self):
        self.monitor = Monitor()
        self.agent = DQNAgent()
        self.hosts = {0: 'h1', 1: 'h2', 2: 'h3'}
        self.host_ips = {0: '10.0.0.1', 1: '10.0.0.2', 2: '10.0.0.3'}
        self.lb_ip = '10.0.0.100'
        self.client_ip = '10.0.0.99'
        self.controller_api = 'http://localhost:8080/stats/flowentry/add'

    def set_flow_rules(self, target_host_idx):
        """Set OpenFlow rules via Ryu REST API to direct traffic to the target host"""
        target_ip = self.host_ips[target_host_idx]
        target_port = target_host_idx + 1  # Port numbers start from 1

        # Delete existing flow rules
        self.delete_flow_rules()
        
        # Các URL Ryu REST API tiêu chuẩn
        add_url = 'http://localhost:8080/stats/flowentry/add'
        
        # Add flow rule from load balancer to server (target_host)
        flow_rule = {
            'dpid': 1,  # Switch ID (s1)
            'priority': 32768,
            'match': {
                'in_port': 4,      # Port connected to load balancer
                'eth_type': 0x0800,  # IPv4
                'ipv4_src': self.lb_ip,
                'ipv4_dst': target_ip
            },
            'actions': [
                {
                    'type': 'OUTPUT',
                    'port': target_port
                }
            ],
            'idle_timeout': 300  # 5 minutes timeout
        }
        
        try:
            # Send flow rule to controller
            response = requests.post(add_url, json=flow_rule)
            if response.status_code != 200:
                print(f"Error setting flow rule: {response.text}")
                return False
            
            # Add flow rule from server to load balancer
            flow_rule = {
                'dpid': 1,
                'priority': 32768,
                'match': {
                    'in_port': target_port,
                    'eth_type': 0x0800,  # IPv4
                    'ipv4_src': target_ip,
                    'ipv4_dst': self.lb_ip
                },
                'actions': [
                    {
                        'type': 'OUTPUT',
                        'port': 4
                    }
                ],
                'idle_timeout': 300  # 5 minutes timeout
            }
            
            response = requests.post(add_url, json=flow_rule)
            if response.status_code != 200:
                print(f"Error setting flow rule: {response.text}")
                return False
            
            # Add flow rule for client to load balancer
            flow_rule = {
                'dpid': 1,
                'priority': 32768,
                'match': {
                    'in_port': 5,      # Port connected to client
                    'eth_type': 0x0800,  # IPv4
                    'ipv4_src': self.client_ip,
                    'ipv4_dst': self.lb_ip
                },
                'actions': [
                    {
                        'type': 'OUTPUT',
                        'port': 4
                    }
                ],
                'idle_timeout': 300  # 5 minutes timeout
            }
            
            response = requests.post(add_url, json=flow_rule)
            if response.status_code != 200:
                print(f"Error setting flow rule: {response.text}")
                return False
                
            # Add flow rule for load balancer to client
            flow_rule = {
                'dpid': 1,
                'priority': 32768,
                'match': {
                    'in_port': 4,
                    'eth_type': 0x0800,  # IPv4
                    'ipv4_src': self.lb_ip,
                    'ipv4_dst': self.client_ip
                },
                'actions': [
                    {
                        'type': 'OUTPUT',
                        'port': 5
                    }
                ],
                'idle_timeout': 300  # 5 minutes timeout
            }
            
            response = requests.post(add_url, json=flow_rule)
            if response.status_code != 200:
                print(f"Error setting flow rule: {response.text}")
                return False
            
            print(f"Flow rules set to direct traffic to {self.hosts[target_host_idx]} ({target_ip})")
            return True
        
        except requests.exceptions.ConnectionError:
            print("ERROR: Cannot connect to Ryu controller API")
            return False

    def delete_flow_rules(self):
        """Delete all flow rules via Ryu REST API"""
        delete_url = 'http://localhost:8080/stats/flowentry/delete'
        
        try:
            # Xóa tất cả flow rules cho datapath id 1 (s1)
            flow_rule = {
                'dpid': 1
            }
            
            response = requests.post(delete_url, json=flow_rule)
            if response.status_code != 200:
                print(f"Error deleting flow rules: {response.text}")
                return False
            else:
                print("All flow rules deleted")
                return True
        except requests.exceptions.ConnectionError:
            print("ERROR: Cannot connect to Ryu controller API")
            return False

    def _generate_traffic(self):
        """Mô phỏng việc tạo lưu lượng truy cập thử nghiệm"""
        print("Simulating test traffic generation...")
        
        time.sleep(2)  # Giả lập thời gian tạo lưu lượng

    def train(self, episodes=30, batch_size=32):
        """Train the DQN agent"""
        print("Starting DQN training...")
        rewards = []
        
        for episode in range(episodes):
            print(f"\nEpisode {episode+1}/{episodes}")
            
            # Initial state
            metrics = self.monitor.collect_data()
            state = self.agent.preprocess_state(metrics)
            
            # Choose an action (server)
            action = self.agent.act(state)
            host = self.hosts[action]
            print(f"Selected host: {host}")
            
            # Execute action (set flow rules)
            self.set_flow_rules(action)
            
            # Wait for the action to take effect and generate traffic
            print("Generating test traffic...")
            self._generate_traffic()
            time.sleep(5)  # Allow time for the effect of the action
            
            # Observe new state
            new_metrics = self.monitor.collect_data()
            next_state = self.agent.preprocess_state(new_metrics)
            
            # Calculate reward
            reward = self.agent.calculate_reward(host, new_metrics)
            print(f"Reward: {reward:.2f}")
            rewards.append(reward)
            
            # Store experience in memory
            done = (episode == episodes - 1)
            self.agent.remember(state, action, reward, next_state, done)
            
            # Training step
            self.agent.replay(batch_size)
            
            # Update target model periodically
            if episode % 5 == 0:
                self.agent.update_target_model()
                
            print(f"Epsilon: {self.agent.epsilon:.4f}")
            
            # Clean up for next episode
            self.delete_flow_rules()
            time.sleep(1)
        
        # Save the trained model
        self.agent.save("dqn_load_balancer.pth")
        
        # Save rewards data
        np.savetxt('rewards.csv', np.column_stack((np.arange(1, len(rewards)+1), rewards)), 
                   delimiter=',', header='episode,reward', comments='')
        
        # Save monitoring data
        self.monitor.save_data()
        
        print("Training completed. Model saved as 'dqn_load_balancer.pth'")

    def run(self, model_path="dqn_load_balancer.pth"):
        """Run the load balancer with the trained model"""
        print("Running load balancer with DQN agent...")
        
        # Load the trained model
        try:
            self.agent.load(model_path)
            print(f"Loaded model from {model_path}")
            self.agent.epsilon = 0.01  # Set exploration rate to minimum for deployment
        except:
            print(f"Could not load model from {model_path}, using untrained model")
        
        while True:
            try:
                print("\nCollecting current metrics...")
                metrics = self.monitor.collect_data()
                state = self.agent.preprocess_state(metrics)
                
                print("State vector:", state)
                
                # Choose best action
                action = self.agent.act(state)
                host = self.hosts[action]
                print(f"Selected optimal host: {host}")
                
                # Execute action
                self.set_flow_rules(action)
                
                # Wait before next decision
                time.sleep(30)
                
            except KeyboardInterrupt:
                print("Load balancer stopped by user")
                self.delete_flow_rules()
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(5)