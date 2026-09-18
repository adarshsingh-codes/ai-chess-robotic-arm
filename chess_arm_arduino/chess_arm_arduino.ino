#include <Servo.h>

// 0 base, 1 shoulder, 2 elbow (MG995) | 3 wrist pitch, 4 wrist roll, 5 gripper (MG90)
const int N = 6;
const int PINS[N] = {3, 5, 6, 9, 10, 11};
const int HOME_POS[N] = {90, 120, 40, 90, 90, 40};   // must match HOME_ANGLES + roll + GRIPPER_OPEN
const int STEP_MS = 12;                               // ms per degree (lower = faster)

Servo servo[N];
int cur[N];

void moveTo(const int tgt[]) {
  int start[N], steps = 0;
  for (int i = 0; i < N; i++) {
    start[i] = cur[i];
    steps = max(steps, abs(tgt[i] - cur[i]));
  }
  for (int k = 1; k <= steps; k++) {          // all joints arrive together
    for (int i = 0; i < N; i++)
      servo[i].write(start[i] + (long)(tgt[i] - start[i]) * k / steps);
    delay(STEP_MS);
  }
  for (int i = 0; i < N; i++) {
    cur[i] = tgt[i];
    servo[i].write(cur[i]);
  }
}

void setup() {
  Serial.begin(115200);
  for (int i = 0; i < N; i++) {
    cur[i] = HOME_POS[i];
    servo[i].attach(PINS[i]);
    servo[i].write(cur[i]);
  }
  Serial.println("READY");
}

void loop() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  int t[N];
  if (sscanf(line.c_str(), "S %d %d %d %d %d %d",
             &t[0], &t[1], &t[2], &t[3], &t[4], &t[5]) == N) {
    for (int i = 0; i < N; i++) t[i] = constrain(t[i], 0, 180);
    moveTo(t);
    delay(100);
    Serial.println("OK");
  } else {
    Serial.println("ERR");
  }
}
