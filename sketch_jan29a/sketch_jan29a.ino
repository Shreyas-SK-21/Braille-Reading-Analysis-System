// ===== ROW MUX (CD4051) =====
#define ROW_S0 2
#define ROW_S1 3
#define ROW_S2 4
#define ROW_DRV 6

// ===== COLUMN MUX (CD74HC4067) =====
#define COL_S0 8
#define COL_S1 9
#define COL_S2 10
// COL_S3 tied to GND

#define ADC_PIN A0

#define ROWS 8
#define COLS 8

// -------- calibration --------
#define CAL_SAMPLES 120

// -------- sensitivity thresholds --------
#define CELL_ACTIVE_THRESHOLD 20
#define TOUCH_ON_WEIGHT  300
#define TOUCH_OFF_WEIGHT 180
#define PEAK_ON  50
#define PEAK_OFF 30

// -------- smoothing --------
#define SMOOTH_ALPHA 0.25

// -------- active reading definition --------
#define ACTIVE_VEL_THRESHOLD 0.15   // cells / second

#define NO_TOUCH_REPORT_MS 10000

// ================= GLOBALS =================
int baseline[ROWS][COLS];

float smoothX = -1, smoothY = -1;
bool touching = false;

unsigned long touchStartTime = 0;
unsigned long noTouchStartTime = 0;
bool reportPrinted = false;

// debounce
int touchConfirm = 0;

// motion state
float prevMX = 0, prevMY = 0;
unsigned long prevMTime = 0;
float prevVX = 0;
float prevVelocity = 0;

// metrics
float totalDistance = 0;        // cells
float sumVelocity = 0;          // cells/s
float sumVelocitySq = 0;        // (cells/s)^2
float sumAccelSq = 0;           // (cells/s^2)^2
float maxVelocity = 0;          // cells/s
int velocitySamples = 0;
int reversals = 0;
float backwardDistance = 0;     // cells
float forwardDistance = 0;      // cells
unsigned long activeTime = 0;   // ms (FIXED definition)

// dwell time
unsigned long dwellTime[ROWS][COLS];
unsigned long lastCellTime = 0;
int lastCellR = -1, lastCellC = -1;

unsigned long lastPrint = 0;

// ================= MUX HELPERS =================
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

// ================= CALIBRATION =================
void calibrateMatrix() {
  Serial.println("Calibrating... DO NOT TOUCH");

  for (int r = 0; r < ROWS; r++) {
    setRow(r);
    digitalWrite(ROW_DRV, HIGH);
    delayMicroseconds(200);

    for (int c = 0; c < COLS; c++) {
      long sum = 0;
      setCol(c);
      delayMicroseconds(120);
      analogRead(ADC_PIN);

      for (int s = 0; s < CAL_SAMPLES; s++) {
        sum += analogRead(ADC_PIN);
        delayMicroseconds(40);
      }
      baseline[r][c] = sum / CAL_SAMPLES;
    }
    digitalWrite(ROW_DRV, LOW);
  }

  Serial.println("Calibration done.\n");
}

// ================= SETUP =================
void setup() {
  Serial.begin(115200);

  pinMode(ROW_S0, OUTPUT);
  pinMode(ROW_S1, OUTPUT);
  pinMode(ROW_S2, OUTPUT);
  pinMode(ROW_DRV, OUTPUT);

  pinMode(COL_S0, OUTPUT);
  pinMode(COL_S1, OUTPUT);
  pinMode(COL_S2, OUTPUT);

  digitalWrite(ROW_DRV, LOW);

  calibrateMatrix();

  Serial.println("time_ms,x_centroid[cells],y_centroid[cells],x_leading[cells],velocity[cells/s]");
}

// ================= LEADING EDGE =================
float computeLeadingEdgeX(int direction, int active[ROWS][COLS]) {
  if (direction >= 0) {
    for (int c = COLS - 1; c >= 0; c--)
      for (int r = 0; r < ROWS; r++)
        if (active[r][c]) return c;
  } else {
    for (int c = 0; c < COLS; c++)
      for (int r = 0; r < ROWS; r++)
        if (active[r][c]) return c;
  }
  return smoothX;
}

// ================= LOOP =================
void loop() {

  long sumW = 0, sumR = 0, sumC = 0;
  int peakDiff = 0;
  int active[ROWS][COLS] = {0};

  // ---------- scan matrix ----------
  for (int r = 0; r < ROWS; r++) {
    setRow(r);
    digitalWrite(ROW_DRV, HIGH);
    delayMicroseconds(150);

    for (int c = 0; c < COLS; c++) {
      setCol(c);
      delayMicroseconds(100);

      int val = analogRead(ADC_PIN);
      int diff = val - baseline[r][c];

      if (diff > CELL_ACTIVE_THRESHOLD) {
        sumW += diff;
        sumR += diff * r;
        sumC += diff * c;
        active[r][c] = 1;
      }

      if (diff > peakDiff)
        peakDiff = diff;
    }
    digitalWrite(ROW_DRV, LOW);
  }

  // ---------- TOUCH ON (debounced) ----------
  if (!touching) {
    if (sumW > TOUCH_ON_WEIGHT && peakDiff > PEAK_ON)
      touchConfirm++;
    else
      touchConfirm = 0;

    if (touchConfirm >= 2) {
      touching = true;
      touchConfirm = 0;

      touchStartTime = millis();
      prevMTime = millis();
      reportPrinted = false;

      totalDistance = sumVelocity = sumVelocitySq = sumAccelSq = 0;
      maxVelocity = 0;
      velocitySamples = reversals = 0;
      backwardDistance = forwardDistance = 0;
      activeTime = 0;

      prevVX = prevVelocity = 0;
      smoothX = smoothY = -1;
      lastCellR = lastCellC = -1;
      memset(dwellTime, 0, sizeof(dwellTime));
    }
  }

  // ---------- TOUCH OFF ----------
  else if (touching && sumW < TOUCH_OFF_WEIGHT && peakDiff < PEAK_OFF) {
    touching = false;
    noTouchStartTime = millis();
  }

  // ---------- TRACKING ----------
  if (touching && sumW > 0) {

    float cx = (float)sumC / sumW;
    float cy = (float)sumR / sumW;

    if (smoothX < 0) {
      smoothX = cx;
      smoothY = cy;
    } else {
      smoothX = smoothX * (1 - SMOOTH_ALPHA) + cx * SMOOTH_ALPHA;
      smoothY = smoothY * (1 - SMOOTH_ALPHA) + cy * SMOOTH_ALPHA;
    }

    unsigned long now = millis();
    float dt = (now - prevMTime) / 1000.0;

    float dx = smoothX - prevMX;
    float dy = smoothY - prevMY;

    if (dt > 0) {
      float dist = sqrt(dx * dx + dy * dy);
      float vel = dist / dt;
      float vx = dx / dt;
      float accel = (vel - prevVelocity) / dt;

      totalDistance += dist;
      sumVelocity += vel;
      sumVelocitySq += vel * vel;
      sumAccelSq += accel * accel;
      velocitySamples++;
      if (vel > maxVelocity) maxVelocity = vel;

      if (vx < 0) backwardDistance += abs(dx);
      else forwardDistance += abs(dx);

      if ((vx > 0 && prevVX < 0) || (vx < 0 && prevVX > 0))
        reversals++;

      // ✅ FIXED ACTIVE READING TIME
      if (vel > ACTIVE_VEL_THRESHOLD) {
        activeTime += now - prevMTime;
      }

      prevVX = vx;
      prevVelocity = vel;
    }

    int cellR = round(smoothY);
    int cellC = round(smoothX);
    if (cellR != lastCellR || cellC != lastCellC) {
      if (lastCellR >= 0 && lastCellC >= 0)
        dwellTime[lastCellR][lastCellC] += now - lastCellTime;
      lastCellTime = now;
      lastCellR = cellR;
      lastCellC = cellC;
    }

    float leadX = computeLeadingEdgeX((dx >= 0) ? 1 : -1, active);

    if (now - lastPrint > 30) {
      Serial.print(now);
      Serial.print(",");
      Serial.print(smoothX, 3);
      Serial.print(",");
      Serial.print(smoothY, 3);
      Serial.print(",");
      Serial.print(leadX, 3);
      Serial.print(",");
      Serial.println(prevVelocity, 3);
      lastPrint = now;
    }

    prevMX = smoothX;
    prevMY = smoothY;
    prevMTime = now;
  }

  // ---------- FINAL REPORT ----------
  if (!touching && !reportPrinted &&
      millis() - noTouchStartTime > NO_TOUCH_REPORT_MS &&
      velocitySamples > 0) {

    float meanVelocity = sumVelocity / velocitySamples;
    float velocityVariance =
      (sumVelocitySq / velocitySamples) - (meanVelocity * meanVelocity);
    float accelRMS = sqrt(sumAccelSq / velocitySamples);
    float backwardRatio =
      backwardDistance / (forwardDistance + backwardDistance + 1e-6);

    Serial.println("\n===== PERFORMANCE METRICS =====");
    Serial.print("Touch duration [s]: ");
    Serial.println((prevMTime - touchStartTime) / 1000.0, 2);

    Serial.print("Active reading time [s]: ");
    Serial.println(activeTime / 1000.0, 2);

    Serial.print("Path length [cells]: ");
    Serial.println(totalDistance, 3);

    Serial.print("Mean velocity [cells/s]: ");
    Serial.println(meanVelocity, 3);

    Serial.print("Peak velocity [cells/s]: ");
    Serial.println(maxVelocity, 3);

    Serial.print("Velocity variance [(cells/s)^2]: ");
    Serial.println(velocityVariance, 4);

    Serial.print("Acceleration RMS [cells/s^2]: ");
    Serial.println(accelRMS, 4);

    Serial.print("Direction reversals [count]: ");
    Serial.println(reversals);

    Serial.print("Backward distance ratio [-]: ");
    Serial.println(backwardRatio, 3);

    Serial.println("===== DWELL MAP [ms] =====");
    for (int r = 0; r < ROWS; r++) {
      for (int c = 0; c < COLS; c++) {
        Serial.print(dwellTime[r][c]);
        Serial.print("\t");
      }
      Serial.println();
    }
    Serial.println("===== END METRICS =====\n");

    reportPrinted = true;
  }
}