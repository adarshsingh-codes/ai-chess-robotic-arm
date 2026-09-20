/*
 * chess_arm_arduino.ino  —  PCA9685 version, hybrid continuous-rotation + positional
 *
 * Base, Shoulder, Elbow (ch 0,1,2)   = continuous-rotation servos, driven by
 *                                      timed relative moves (no position feedback).
 * Wrist Pitch, Wrist Roll, Gripper   = normal positional servos, driven by
 *                                      direct pulse mapping (ch 4, 3, 5).
 *
 * Laptop sends:  "S <base> <shoulder> <elbow> <pitch> <roll> <grip>\n"  (0-180, absolute)
 * Replies "OK" when the move finishes, "ERR" on a bad line. Also accepts "LIMP".
 *
 * IMPORTANT: base/shoulder/elbow have no position feedback. On boot, the
 * firmware ASSUMES the arm is physically at HOME (90, 120, 40) already —
 * position it there by hand before powering on / before running main.py.
 */

#include <Wire.h>
#include <math.h>
#include <Adafruit_PWMServoDriver.h>

#define PCA9685_ADDR 0x40
#define PWM_FREQ     50
#define OE_PIN       4
#define USE_OE_PIN   1

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver(PCA9685_ADDR);

const int N = 6;

// ---- Continuous-rotation joints: base=0, shoulder=1, elbow=2 (physical ch 0,1,2) ----
#define STOP_PULSE   307
#define DEFLECTION   78     // pulse offset from STOP_PULSE for full commanded speed
#define SPEED_DPS    180.0  // calibrated deg/sec at this deflection
#define POS_FACTOR   1.25   // CCW (positive delta) duration correction
#define NEG_FACTOR   1.0    // CW (negative delta) duration correction

float curAngle[3];   // software-tracked angle — only as accurate as the last real position

// ---- Positional joints: wrist pitch=3, wrist roll=4, gripper=5 ----
// Physical channel for each (pitch->ch4, roll->ch3, gripper->ch5):
const uint8_t POS_CH[3]  = {4, 3, 5};
int PULSE_MIN[3] = {150, 150, 150};   // wristPitch, wristRoll, gripper — from your empirical claw calibration
int PULSE_MAX[3] = {300, 300, 300};

int ANG_MIN[N] = {0,   0,   0,   0,   0,   0};
int ANG_MAX[N] = {180, 180, 180, 180, 180, 180};

const int HOME_POS[N] = {90, 120, 40, 90, 90, 40};   // base, shoulder, elbow, pitch, roll, grip

char buf[64];
uint8_t bufIdx = 0;

uint16_t contPulse(int dir) {   // dir: +1 CCW, -1 CW, 0 stop
  if (dir == 0) return STOP_PULSE;
  return dir > 0 ? (STOP_PULSE + DEFLECTION) : (STOP_PULSE - DEFLECTION);
}

void writePosJoint(int i, int deg) {   // i = 3, 4, 5
  deg = constrain(deg, ANG_MIN[i], ANG_MAX[i]);
  int k = i - 3;
  pwm.setPWM(POS_CH[k], 0, map(deg, 0, 180, PULSE_MIN[k], PULSE_MAX[k]));
}

void allOff() {
  for (uint8_t i = 0; i < 16; i++) pwm.setPWM(i, 0, 4096);
}

void moveTo(const int tgt[]) {
  unsigned long dur[3];
  bool done[3];
  unsigned long start = millis();

  for (int i = 0; i < 3; i++) {
    float delta = (float)tgt[i] - curAngle[i];
    if (fabs(delta) < 0.5) {
      dur[i] = 0;
      done[i] = true;
      pwm.setPWM(i, 0, 4096);
      continue;
    }
    int dir = (delta > 0) ? 1 : -1;
    float factor = (delta > 0) ? POS_FACTOR : NEG_FACTOR;
    dur[i] = (unsigned long)((fabs(delta) / SPEED_DPS) * 1000.0 * factor);
    done[i] = false;
    pwm.setPWM(i, 0, contPulse(dir));
  }

  // Wrist pitch/roll + gripper: positional, set immediately, they ramp on their own.
  for (int i = 3; i < N; i++) writePosJoint(i, tgt[i]);

  // Let each continuous joint run for its own duration, cutting its signal
  // the instant IT is done (not waiting for the slowest one).
  while (!(done[0] && done[1] && done[2])) {
    unsigned long elapsed = millis() - start;
    for (int i = 0; i < 3; i++) {
      if (!done[i] && elapsed >= dur[i]) {
        pwm.setPWM(i, 0, 4096);   // cut signal -> stops
        done[i] = true;
      }
    }
  }
  for (int i = 0; i < 3; i++) curAngle[i] = tgt[i];

  delay(150);   // let the 3 positional servos visually settle
}

void setup() {
  Serial.begin(115200);

#if USE_OE_PIN
  pinMode(OE_PIN, OUTPUT);
  digitalWrite(OE_PIN, HIGH);
#endif

  pwm.begin();
  pwm.setOscillatorFrequency(27000000);
  pwm.setPWMFreq(PWM_FREQ);
  allOff();

#if USE_OE_PIN
  digitalWrite(OE_PIN, LOW);
#endif

  // Continuous-rotation joints: trust the arm is physically at HOME already.
  curAngle[0] = HOME_POS[0];
  curAngle[1] = HOME_POS[1];
  curAngle[2] = HOME_POS[2];
  for (int i = 0; i < 3; i++) pwm.setPWM(i, 0, 4096);   // limp, matches your tested behavior

  // Positional joints: actually home for real.
  for (int i = 3; i < N; i++) {
    writePosJoint(i, HOME_POS[i]);
    delay(300);
  }

  Serial.println("READY - confirm base/shoulder/elbow are physically at HOME before sending moves");
}

void handle(const char* cmd) {
  int t[N];
  if (sscanf(cmd, "S %d %d %d %d %d %d",
             &t[0], &t[1], &t[2], &t[3], &t[4], &t[5]) == N) {
    for (int i = 0; i < N; i++) t[i] = constrain(t[i], ANG_MIN[i], ANG_MAX[i]);
    moveTo(t);
    Serial.println("OK");
  } else if (strncmp(cmd, "LIMP", 4) == 0) {
    allOff();
    Serial.println("OK");
  } else {
    Serial.println("ERR");
  }
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (bufIdx > 0) {
        buf[bufIdx] = '\0';
        bufIdx = 0;
        handle(buf);
      }
    } else if (bufIdx < 63) {
      buf[bufIdx++] = c;
    }
  }
}