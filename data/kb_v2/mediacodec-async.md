# Using MediaCodec in asynchronous mode

## Callback mode
Call `setCallback` before `configure`; the codec then reports input buffers, output buffers,
format changes, and errors through the callback, on a handler thread you choose.

## Buffer handling
Queue input only from `onInputBufferAvailable`, release every output buffer you receive, and treat
`onOutputFormatChanged` as the authoritative output format. Holding output buffers stalls the
decoder.
