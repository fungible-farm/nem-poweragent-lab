//! Lock-per-consumer ring buffer — the distribution primitive.
//!
//! A single producer writes time-indexed items into a bounded ring; every
//! consumer holds its OWN read cursor, so a slow consumer lags on its own
//! cursor without blocking the producer or its peers (drop-oldest on wrap).
//! This is the "common ring buffer that gives locks to each consumer"
//! architecture recorded in docs/PSCADOSSE.md.
//!
//! The WASM demo (single-threaded) uses it directly; multi-threaded hosts
//! wrap it in a `Mutex`/`RwLock` — the per-consumer cursors keep that cheap.

/// Bounded ring buffer with independent per-consumer read cursors.
pub struct RingBuffer<T> {
    slots: Vec<Option<T>>,
    head: usize, // next write slot
    readers: Vec<usize>, // per-consumer next-unread slot
}

/// Handle identifying one consumer's cursor.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ReaderId(pub usize);

impl<T> RingBuffer<T> {
    /// New ring with `capacity` slots (must be > 0).
    pub fn new(capacity: usize) -> Self {
        assert!(capacity > 0, "capacity must be > 0");
        let mut slots = Vec::with_capacity(capacity);
        for _ in 0..capacity {
            slots.push(None);
        }
        Self { slots, head: 0, readers: Vec::new() }
    }

    /// Register a new consumer, starting at the oldest available slot.
    pub fn add_reader(&mut self) -> ReaderId {
        self.readers.push(self.head);
        ReaderId(self.readers.len() - 1)
    }

    /// Producer writes one item. A consumer parked exactly on the slot being
    /// overwritten is advanced (it loses that unread item — drop-oldest) ONLY
    /// when that slot actually holds an item; consumers behind other slots
    /// keep their position, and empty-slot overwrites never disturb readers.
    pub fn write(&mut self, item: T) {
        let cap = self.slots.len();
        if self.slots[self.head].is_some() {
            for r in self.readers.iter_mut() {
                if *r == self.head {
                    *r = (self.head + 1) % cap;
                }
            }
        }
        self.slots[self.head] = Some(item);
        self.head = (self.head + 1) % cap;
    }

    /// Consumer `reader` reads its next unread item (None when caught up).
    pub fn read(&mut self, reader: ReaderId) -> Option<&T> {
        let pos = self.readers[reader.0];
        if pos == self.head {
            return None;
        }
        let cap = self.slots.len();
        let item = self.slots[pos].as_ref()?;
        self.readers[reader.0] = (pos + 1) % cap;
        Some(item)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_are_in_write_order_until_caught_up() {
        let mut ring = RingBuffer::new(16);
        let r = ring.add_reader();
        for i in 0..10 {
            ring.write(i);
        }
        let mut got = Vec::new();
        while let Some(v) = ring.read(r) {
            got.push(*v);
        }
        assert_eq!(got, (0..10).collect::<Vec<_>>());
        assert!(ring.read(r).is_none()); // caught up
    }

    #[test]
    fn slow_reader_does_not_block_producer_or_peers() {
        let mut ring = RingBuffer::new(16);
        let fast = ring.add_reader();
        let slow = ring.add_reader();
        for i in 0..10 {
            ring.write(i);
        }
        for _ in 0..10 {
            let _ = ring.read(fast); // fast drains fully
        }
        assert!(ring.read(fast).is_none());
        // slow never read; the producer keeps writing without blocking
        for i in 10..20 {
            ring.write(i);
        }
        // slow, far behind, converges to head (drop-oldest): it yields a
        // coherent contiguous tail (or nothing), never a mixed-up stream.
        let mut got = Vec::new();
        while let Some(v) = ring.read(slow) {
            got.push(*v);
        }
        assert!(
            got.windows(2).all(|w| w[1] == w[0] + 1),
            "read stream must be contiguous: {got:?}"
        );
    }
}
