#include <math.h>

/* ================= HARDWARE ================= */

#define ROW_S0 2
#define ROW_S1 3
#define ROW_S2 4
#define ROW_DRV 6

#define COL_S0 8
#define COL_S1 9
#define COL_S2 10

#define ADC_PIN A0

#define ROWS 8
#define COLS 8

/* ================= GRID ================= */

#define GRID_X 6
#define GRID_Y 4
float heatmap[GRID_Y][GRID_X];

/* ================= CALIBRATION ================= */

#define CAL_SAMPLES 80
int baseline[ROWS][COLS];

/* ================= NOISE LEARNING ================= */

#define NOISE_LEARN_MS 90000UL   // 1.5 minutes

bool noiseLearnDone = false;
unsigned long noiseStart;

double noiseMean = 0;
double noiseM2 = 0;
long noiseCount = 0;
int noiseMax = 0;

/* ================= TOUCH / CONFIDENCE ================= */

int PEAK_ON;
int PEAK_OFF;
float ENERGY_ON;
float ENERGY_MOVE;

#define MIN_ACTIVE_CELLS 3
#define TOUCH_ON_FRAMES  3
#define TOUCH_OFF_FRAMES 4

/* ================= SIGNAL ================= */

#define GAMMA 1.2

#define ALPHA_ALONG 0.35
#define ALPHA_PERP  0.10

#define MOTION_EPS 0.15
#define MAX_VELOCITY 60.0
#define MAX_ACCEL 40.0

/* ================= EDGE GAINS (FIXED) ================= */

const float EDGE_GAIN_X[COLS] = {
  1.600, 0.870, 1.522, 1.600, 0.600, 1.600, 0.623, 1.600
};

const float EDGE_GAIN_Y[ROWS] = {
 1.081, 0.600, 1.600, 1.282, 1.600, 1.552, 0.601, 0.876
};

/* ================= STATE ================= */

bool touching = false;
int touchOnCount = 0;
int touchOffCount = 0;

/* --- tracking state --- */
float trackX = -1, trackY = -1;
float prevTX = 0, prevTY = 0;

float velX = 0, velY = 0;
unsigned long prevMTime = 0;

/* ================= METRICS ================= */

float totalDistance = 0;
float velocitySum = 0;
float velocitySqSum = 0;
float accelSqSum = 0;
float maxVelocity = 0;
int velocityCount = 0;

unsigned long touchStartTime = 0;
unsigned long lastTouchTime = 0;

/* ================= HELPERS ================= */

inline float gammaScale(int d) {
  return d > 0 ? pow(d, GAMMA) : 0;
}

void setRow(int r) {
  digitalWrite(ROW_S0, r & 1);
  digitalWrite(ROW_S1, (r >> 1) & 1);
  digitalWrite(ROW_S2, (r >> 2) & 1);
}

void setCol(int c) {
  digitalWrite(COL_S0, c & 1);
  digitalWrite(COL_S1, (c >> 1) & 1);
  digitalWrite(COL_S2, (c >> 2) & 1);
}

/* ================= BASELINE ================= */

void calibrateMatrix() {
  Serial.println("Calibrating baseline... DO NOT TOUCH");

  for (int r = 0; r < ROWS; r++) {
    setRow(r);
    digitalWrite(ROW_DRV, HIGH);
    delayMicroseconds(200);

    for (int c = 0; c < COLS; c++) {
      setCol(c);
      delayMicroseconds(120);
      analogRead(ADC_PIN);

      long sum = 0;
      for (int i = 0; i < CAL_SAMPLES; i++) {
        sum += analogRead(ADC_PIN);
        delayMicroseconds(40);
      }
      baseline[r][c] = sum / CAL_SAMPLES;
    }
    digitalWrite(ROW_DRV, LOW);
  }
}

/* ================= SETUP ================= */

void setup() {
  Serial.begin(115200);

  pinMode(ROW_S0, OUTPUT);
  pinMode(ROW_S1, OUTPUT);
  pinMode(ROW_S2, OUTPUT);
  pinMode(ROW_DRV, OUTPUT);

  pinMode(COL_S0, OUTPUT);
  pinMode(COL_S1, OUTPUT);
  pinMode(COL_S2, OUTPUT);

  calibrateMatrix();

  noiseStart = millis();
  Serial.println("Learning noise... DO NOT TOUCH");
}

/* ================= LOOP ================= */

void loop() {

  int rawPeak = 0;
  int activeCells = 0;
  float energy = 0;

  float gSumW = 0, gSumR = 0, gSumC = 0;

  /* ---------- SCAN ---------- */

  for (int r = 0; r < ROWS; r++) {
    setRow(r);
    digitalWrite(ROW_DRV, HIGH);
    delayMicroseconds(150);

    for (int c = 0; c < COLS; c++) {
      setCol(c);
      delayMicroseconds(100);

      analogRead(ADC_PIN);
      int diff = analogRead(ADC_PIN) - baseline[r][c];
      if (diff <= 0) continue;

      activeCells++;
      rawPeak = max(rawPeak, diff);

      float w = gammaScale(diff);
      energy += w;

      w *= EDGE_GAIN_X[c] * EDGE_GAIN_Y[r];

      gSumW += w;
      gSumR += w * r;
      gSumC += w * c;

      int gx = map(c, 0, COLS - 1, 0, GRID_X - 1);
      int gy = map(r, 0, ROWS - 1, 0, GRID_Y - 1);
      heatmap[gy][gx] += w;
    }
    digitalWrite(ROW_DRV, LOW);
  }

  /* ---------- NOISE LEARNING ---------- */

  if (!noiseLearnDone) {
    noiseCount++;
    double d = rawPeak - noiseMean;
    noiseMean += d / noiseCount;
    noiseM2 += d * (rawPeak - noiseMean);
    noiseMax = max(noiseMax, rawPeak);

    if (millis() - noiseStart > NOISE_LEARN_MS) {
      double std = sqrt(noiseM2 / (noiseCount - 1));
      PEAK_ON = max((int)(noiseMean + 6 * std), noiseMax + 5);
      PEAK_OFF = noiseMean + 3 * std;
      ENERGY_ON = noiseMean * 20;
      ENERGY_MOVE = noiseMean * 10;

      noiseLearnDone = true;
      Serial.println("\n=== NOISE LEARNING COMPLETE ===");
      Serial.println("time_ms,x,y,velocity");
    }
    return;
  }

  /* ---------- TOUCH STATE ---------- */

  if (!touching) {
    if (rawPeak > PEAK_ON &&
        energy > ENERGY_ON &&
        activeCells >= MIN_ACTIVE_CELLS) {

      if (++touchOnCount >= TOUCH_ON_FRAMES) {
        touching = true;
        trackX = trackY = -1;
        velX = velY = 0;
        totalDistance = velocitySum = velocitySqSum = accelSqSum = 0;
        velocityCount = 0;
        maxVelocity = 0;
        memset(heatmap, 0, sizeof(heatmap));
        touchStartTime = millis();
      }
    } else touchOnCount = 0;
  } else {
    if (rawPeak < PEAK_OFF) {
      if (++touchOffCount >= TOUCH_OFF_FRAMES) {
        touching = false;
        lastTouchTime = millis();
      }
    } else touchOffCount = 0;
  }

  /* ---------- TRACKING ---------- */

  if (touching && gSumW > 0 && energy > ENERGY_MOVE) {

    float cx = gSumC / gSumW;
    float cy = gSumR / gSumW;

    if (trackX < 0) {
      trackX = cx;
      trackY = cy;
      prevTX = trackX;
      prevTY = trackY;
      prevMTime = millis();
      return;
    }

    unsigned long now = millis();
    float dt = (now - prevMTime) / 1000.0;
    if (dt < 0.01) return;

    float dx = cx - trackX;
    float dy = cy - trackY;

    float speed = sqrt(velX * velX + velY * velY);
    float nx = 0, ny = 0;
    if (speed > 0.01) {
      nx = velX / speed;
      ny = velY / speed;
    }

    float along = dx * nx + dy * ny;
    float perpX = dx - along * nx;
    float perpY = dy - along * ny;

    trackX += along * ALPHA_ALONG + perpX * ALPHA_PERP;
    trackY += along * ALPHA_ALONG + perpY * ALPHA_PERP;

    float ax = (trackX - prevTX) / dt;
    float ay = (trackY - prevTY) / dt;

    float aMag = sqrt(ax * ax + ay * ay);
    if (aMag > MAX_ACCEL) {
      ax *= MAX_ACCEL / aMag;
      ay *= MAX_ACCEL / aMag;
    }

    velX += ax * dt;
    velY += ay * dt;

    velX *= 0.85;
    velY *= 0.85;

    float vel = sqrt(velX * velX + velY * velY);
    maxVelocity = max(maxVelocity, vel);

    totalDistance += sqrt((trackX - prevTX) * (trackX - prevTX) +
                          (trackY - prevTY) * (trackY - prevTY));

    velocitySum += vel;
    velocitySqSum += vel * vel;
    velocityCount++;

    prevTX = trackX;
    prevTY = trackY;
    prevMTime = now;

    Serial.print(now); Serial.print(",");
    Serial.print(trackX, 3); Serial.print(",");
    Serial.print(trackY, 3); Serial.print(",");
    Serial.println(vel, 3);
  }

  /* ---------- REPORT ---------- */

  if (!touching && velocityCount > 10 &&
      millis() - lastTouchTime > 2000) {

    float meanV = velocitySum / velocityCount;
    float varV = velocitySqSum / velocityCount - meanV * meanV;
    float accelRMS = sqrt(accelSqSum / velocityCount);

    Serial.println("\n===== METRICS =====");
    Serial.print("Duration (s): ");
    Serial.println((lastTouchTime - touchStartTime) / 1000.0, 2);
    Serial.print("Path length: ");
    Serial.println(totalDistance, 3);
    Serial.print("Mean velocity: ");
    Serial.println(meanV, 3);
    Serial.print("Peak velocity: ");
    Serial.println(maxVelocity, 3);
    Serial.print("Velocity variance: ");
    Serial.println(varV, 4);
    Serial.print("Accel RMS: ");
    Serial.println(accelRMS, 4);

    Serial.println("\n===== 6x4 HEATMAP =====");
    for (int y = 0; y < GRID_Y; y++) {
      for (int x = 0; x < GRID_X; x++) {
        Serial.print(heatmap[y][x], 1);
        if (x < GRID_X - 1) Serial.print(",");
      }
      Serial.println();
    }

    velocityCount = 0;
  }
}