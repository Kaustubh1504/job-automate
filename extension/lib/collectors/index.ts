// Importing this module self-registers every collector (side-effect imports),
// mirroring the pipeline's "import the package -> all parsers register" pattern.
// Add a new board by dropping a module here and adding one import line.
import './linkedin';
import './indeed';
import './handshake';
import './nuworks';
