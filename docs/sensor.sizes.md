# Image circles and sensor sizes


## What do “1 inch” and “1/2.3 inch” actually mean?

Those fractions are legacy video‑tube designations and *not* the physical diagonal of the sensor. For example:

| Marketing name | Actual diagonal | Typical crop factor* |
|----------------|-----------------|----------------------|
| “Full‑frame” (35 mm stills) | 43 mm | 1.0× (reference) |
| Micro‑Four‑Thirds | 22 mm | ~2.0× |
| “1 inch” | 16 mm | ~2.7× |
| Raspberry Pi HQ (IMX477, sold as “1/2.3 inch”) | 7.9 mm | ~5.6× |

As we can see, the smaller the sensor the larger the crop factor with regards to the 35mm standard reference.

C/CS Mounts

C and CS lenses were designed for small‑format video and security cameras, so their image circles perfectly cover the IMX477. The Raspberry Pi HQ board also has a built‑in back‑focus adjustment 

---

## What if I really want wide shots?

You have two realistic options:

1. **Speed‑boosters and focal reducers**  
   These compress a larger image circle down onto the small sensor, regaining some angle of view. They cost more than the camera and introduce extra optical surfaces, but can work in a pinch.  
2. **A bigger sensor**  
   Stepping up to something like the IMX585 (“1/1.2 inch”) cuts the crop factor roughly in half. At that point, adapting Micro‑Four‑Thirds or vintage 35 mm lenses begins to make practical sense.

---

##  Buying tips for beginners

1. **Start with the stock 6 – 12 mm Raspberry Pi zoom**  
   It teaches you which focal lengths you genuinely use.  
2. **Add one or two vintage C‑mount primes**  
   Look for 8 mm or 12 mm lenses from brands such as Kern‑Paillard, Computar, or Angénieux. They’re small, sharp, and often under €100.  
3. **Master back‑focus adjustment**  
   The HQ board’s silver ring lets you dial in infinity focus without spacers—a lifesaver when swapping lenses.  
4. **Only then consider adapters**  
   If you’re bumping into the limits of the sensor rather than the lens, that’s the signal to explore larger sensors like the IMX585 plus an MFT or EF adapter.

---

## 6  Rules of thumb (bookmark these)

- **Focal length math:**  
  Effective 35 mm focal length = *Lens focal length × Crop factor*.  
  (e.g., 12 mm × 5.6 ≈ 67 mm portrait.)  
- **Image circle > sensor diagonal.**  
  If the spec sheet doesn’t list it, assume C/CS lenses cover up to 11 mm and nothing larger.  
- **Big‑sensor lenses on tiny sensors ≠ better image.**  
  Quality comes from glass *matched* to the sensor, not size alone.

---

### TL;DR

For the Raspberry Pi HQ camera (IMX477), **vintage C‑mount lenses are your best friends**—they cover the sensor perfectly, cost little, and keep the rig small.  
If you crave a wider field of view or shallower depth of field that feels “cinematic,” consider upgrading the sensor itself (e.g., IMX585) before chasing exotic adapters and full‑frame glass.

Happy shooting, and may your pixels always land exactly where you intend!
