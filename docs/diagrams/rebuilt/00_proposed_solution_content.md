## The problem

- GPS loss interrupts navigation in tunnels and dense streets.
- Unaided phone sensors accumulate position error.

## What’s different

- No vehicle connection or wheel sensors.
- Learned uncertainty controls correction strength.
- Models run locally on the phone.

## Our solution

Navigation through GPS outages using the phone’s own motion

- Auto-calibration aligns the phone to the vehicle.
- AI estimates speed from phone motion.
- Fusion combines speed, heading and offline roads.
- Stop detection limits drift while stationary.
- GPS corrections blend back when signals return.

10 Hz position updates. Offline navigation.
