import http from 'k6/http';
import { check } from 'k6';

// Ramp virtual users up, hold, then down — enough request volume to push the
// pods' CPU past the HPA's 50% target and trigger scale-out.
export const options = {
  stages: [
    { duration: '30s', target: 60 }, // ramp up to 60 VUs
    { duration: '2m', target: 60 },  // hold the load so the HPA reacts
    { duration: '30s', target: 0 },  // ramp down to let it scale back in
  ],
};

export default function () {
  const res = http.get('http://localhost/');
  check(res, { 'status is 200': (r) => r.status === 200 });
}
