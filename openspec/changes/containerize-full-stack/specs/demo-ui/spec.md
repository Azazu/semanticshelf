## MODIFIED Requirements

### Requirement: The interface is a client of the service and nothing else

The interface SHALL reach the service only over its HTTP API. It SHALL NOT open
the database, SHALL NOT read or write the media root, SHALL NOT load an
embedding model, and SHALL NOT import the service's own code. Every picture it
displays SHALL be fetched from an address the API gave it.

It SHALL be configured by the address of the service: the address the interface
itself calls, and — where a browser cannot use that one — the address the
pictures are given to the browser under. The second SHALL default to the first,
so a deployment where they are the same is configured by one setting, and the
interface SHALL NOT invent either of them from anything but configuration.

Both SHALL have defaults that match the documented development port.

#### Scenario: The interface does not import the service
- **WHEN** the interface's own modules are read, including the imports inside
  their functions
- **THEN** none of them imports the service's code — which is what a check can
  answer; that the interface opens no database, reads no media root and loads no
  model is held by there being nothing in it that could, and by review of these
  few modules

#### Scenario: Where a picture comes from
- **WHEN** the interface shows any picture
- **THEN** it is addressed by a URL the API returned, and the interface never
  reads the bytes itself

#### Scenario: A service somewhere else
- **WHEN** the interface is told a different address for the service
- **THEN** it talks to that one, and nothing else about it changes

#### Scenario: The interface's server and the browser are on different networks
- **WHEN** the interface is told one address to call and another for the
  pictures — the case a container stack creates, where the service's name
  resolves for the interface's server and not for the browser
- **THEN** its own requests go to the first and every picture it shows is
  addressed by the second

#### Scenario: One address is enough when one address is true
- **WHEN** the interface is told only the address it calls
- **THEN** the pictures are addressed by that same one, and nothing about the
  configuration got harder

#### Scenario: The service is not answering
- **WHEN** the service cannot be reached at all
- **THEN** the page says so in a sentence a person can act on, and the
  interface stays usable rather than failing with a stack trace
