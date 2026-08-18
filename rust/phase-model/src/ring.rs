//! Lock-per-consumer ring buffer — the distribution primitive.
//!
//! A single producer writes time-indexed items into a bounded ring; every
//! consumer holds its OWN read cursor, so a slow consumer lags on its own
//! cursor without blocking the producer or its peers (drop-oldest on wrap).
//! This is the "common ring buffer that gives locks to each consumer"
//! architecture recorded in docs/PSCADOSSE.md.
//!
//! Correctness model: monotonic logical indices. Each item gets a global
//! write index; a reader's cursor is the NEXT LOGICAL INDEX it will read
//! (not a raw slot). The producer tracks `written` (next index to write) and
//! `dropped` (the oldest index still in the ring). A reader behind `dropped`
//! has lost items (drop-oldest) and skips straight to `dropped`; a reader at
//! `written` is caught up. This removes the slot/empty ambiguity a raw
//! cursor introduces (the bug: returning "caught up" at the write frontier
//! while older surviving items were still unread).
//!
//! The WASM demo (single-threaded) uses it directly; multi-threaded hosts
//! wrap it in a `Mutex`/`RwLock` — the per-consumer cursors keep that cheap.

/// Bounded ring buffer with independent per-consumer read cursors.
pub struct RingBuffer<T> {
    slots: Vec<Option<T>>,
    written: u64,       // next logical index to write (total writes so far)
    dropped: u64,       // logical index of the oldest item still available
    readers: Vec<u64>,  // per-consumer next logical index to read
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
        Self { slots, written: 0, dropped: 0, readers: Vec::new() }
    }

    /// Register a new consumer, starting at the oldest available item.
    pub fn add_reader(&mut self) -> ReaderId {
        self.readers.push(self.dropped);
        ReaderId(self.readers.len() - 1)
    }

    /// Number of items written so far.
    pub fn written(&self) -> u64 {
        self.written
    }

    /// Producer writes one item (logical index `written`). Once the ring has
    /// wrapped, the oldest item is dropped on each write.
    pub fn write(&mut self, item: T) {
        let cap = self.slots.len() as u64;
        let slot = (self.written % cap) as usize;
        self.slots[slot] = Some(item);
        self.written += 1;
        if self.written > cap {
            self.dropped = self.written - cap;
        }
    }

    /// Consumer `reader` reads its next unread item, in write order.
    ///
    /// Returns None only when the reader is caught up (nothing newer has been
    /// written). A reader that fell behind the drop-oldest frontier skips
    /// forward to `dropped` — it lost those items but keeps a contiguous
    /// stream from there (never out of order).
    pub fn read(&mut self, reader: ReaderId) -> Option<&T> {
        let cap = self.slots.len() as u64;
        let mut k = self.readers[reader.0];
        if k >= self.written {
            return None; // caught up
        }
        if k < self.dropped {
            k = self.dropped; // lost items to drop-oldest; skip forward
            self.readers[reader.0] = k;
        }
        let item = self.slots[(k % cap) as usize].as_ref()?;
        self.readers[reader.0] = k + 1;
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
        // slow, far behind, skips to the drop-oldest frontier and reads a
        // coherent contiguous tail (never a mixed-up stream).
        let mut got = Vec::new();
        while let Some(v) = ring.read(slow) {
            got.push(*v);
        }
        assert!(
            got.windows(2).all(|w| w[1] == w[0] + 1),
            "read stream must be contiguous: {got:?}"
        );
    }

    #[test]
    fn bumped_reader_still_reads_surviving_older_items() {
        // Regression: a reader parked exactly on a slot that gets overwritten
        // must NOT be treated as "caught up" -- it still has older surviving
        // items to read (the old bug returned None at the write frontier).
        let mut ring = RingBuffer::new(8);
        let a = ring.add_reader();
        for i in 0..8 {
            ring.write(i); // fills the ring; nothing dropped yet
        }
        ring.write(8); // overwrites slot 0 (item 0 dropped); a is parked at 0
        let mut got = Vec::new();
        while let Some(v) = ring.read(a) {
            got.push(*v);
        }
        // a loses only item 0; items 1..=8 survive in order.
        assert_eq!(got, (1..=8).collect::<Vec<_>>());
    }
}
