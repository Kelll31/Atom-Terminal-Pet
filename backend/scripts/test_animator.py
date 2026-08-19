import math
import time

def lerp(a, b, t):
    return a + (b - a) * t

class SimulatedAnimator:
    def __init__(self):
        self.leftEye = {'x': 30, 'y': 40}
        self.targetLeftEye = {'x': 30, 'y': 40}
        self.eyeHeight = 25
        self.targetEyeHeight = 25
        self.saccadeX = 0
        self.saccadeY = 0
        self.frameCount = 0

    def update_targets(self, pitch, roll, emotion, now):
        self.frameCount += 1
        baseLeftX = 30
        baseY = 40
        breathOffset = math.sin(now * 0.0015) * 2.0
        
        parallaxX = max(min(roll * 0.25, 12.0), -12.0)
        parallaxY = max(min(pitch * 0.25, 12.0), -12.0)

        self.targetLeftEye['x'] = baseLeftX + parallaxX + self.saccadeX
        self.targetLeftEye['y'] = baseY + parallaxY + self.saccadeY + breathOffset

        if emotion == "HAPPY":
            self.targetEyeHeight = 8
            self.targetLeftEye['y'] -= 4
            self.targetLeftEye['y'] += math.sin(now * 0.008) * 3

    def render_frame(self):
        dt = 0.2
        self.leftEye['x'] = lerp(self.leftEye['x'], self.targetLeftEye['x'], dt)
        self.leftEye['y'] = lerp(self.leftEye['y'], self.targetLeftEye['y'], dt)
        self.eyeHeight = lerp(self.eyeHeight, self.targetEyeHeight, dt)

animator = SimulatedAnimator()
try:
    for i in range(100):
        now = i * 33 # 30 fps
        animator.update_targets(5.0, -2.0, "HAPPY", now)
        animator.render_frame()
        # Ensure no NaNs or Inf
        if math.isnan(animator.leftEye['x']) or math.isnan(animator.leftEye['y']):
            raise ValueError("NaN detected in simulation!")
        if math.isinf(animator.leftEye['x']) or math.isinf(animator.leftEye['y']):
            raise ValueError("Infinity detected in simulation!")
    print("Simulation passed: No NaN or Infinity detected in animation math.")
except Exception as e:
    print(f"Simulation failed: {e}")
