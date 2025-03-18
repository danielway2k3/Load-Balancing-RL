```
                         ┌────────────────┐
                         │                │
                         │  run_pipeline  │ (điều phối)
                         │                │
                         └───────┬────────┘
                                 │
           ┌───────────┬────────┴────────┬────────────┐
           ▼           ▼                 ▼            ▼
┌──────────────┐ ┌──────────┐ ┌────────────────┐ ┌──────────┐
│              │ │          │ │                │ │          │
│ ryu-manager  │ │ mininet  │ │ traffic_gen    │ │ RL train │
│ (controller) │ │(topology)│ │ (load creator) │ │ (agent)  │
│              │ │          │ │                │ │          │
└──────┬───────┘ └────┬─────┘ └────────┬───────┘ └────┬─────┘
       │              │                │              │
       └───────┬──────┘                │              │
               │                       │              │
        ┌──────▼───────┐               │              │
        │              │               │              │
        │   Network    │◄──────────────┘              │
        │Infrastructure│                              │
        │              │◄─────────────────────────────┘
        └──────────────┘
         (Flow Tables)
```

## Vai tro cua tung file:
1. ryu_controller.py
Bo dieu khien OpenFlow voi Ryu

2. main.py:
Thiet lap moi truong mang ao Mininet:
```
sudo python3 main.py
```

3. control.py
Dong vai tro chung gian de ket noi RL(DQN) va controller Ryu

4. 
