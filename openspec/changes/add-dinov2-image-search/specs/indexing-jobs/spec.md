## MODIFIED Requirements

### Requirement: Work is created with the asset, or not at all

Storing an asset SHALL create one unit of work per enabled model in the same
transaction as the asset itself. An asset SHALL NOT exist without the work its
vectors need, and work SHALL NOT exist for an asset that was never stored. The
request that created the asset SHALL NOT wait for that work.

Work MAY also be created later, for assets that are already stored and have no
vector for a model — which is what happens when a model is added to a service
that already holds pictures. Creating it SHALL be an operator's act, never the
service's own: nothing SHALL queue work by itself at start or in the background.
Such work SHALL be created only for an asset that has, for that model, neither a
vector nor work that is waiting, running or failed, and SHALL be
indistinguishable afterwards from the work an upload creates.

Asking twice SHALL create nothing the second time, and two operators asking at
the same time SHALL NOT create the same work twice. Work that failed SHALL NOT
be created again this way — an explicit reset remains the only thing that runs
failed work again — and the operator SHALL be told how many assets were passed
over for that reason, so that "nothing was queued" can be told apart from
"nothing needed queueing".

#### Scenario: An asset is stored
- **WHEN** an asset is stored while two models are enabled
- **THEN** exactly two units of work exist for it, each naming one model, and
  each waiting to be done

#### Scenario: Storing the asset fails
- **WHEN** storing an asset fails after its work would have been created
- **THEN** neither the asset nor any work for it exists

#### Scenario: The caller does not wait
- **WHEN** an asset is uploaded
- **THEN** the answer arrives without waiting for any vector to be computed

#### Scenario: A model arrives after the pictures did
- **WHEN** an operator asks for the missing work of a model, and the store holds
  assets with neither a vector for it nor work of their own for it
- **THEN** one unit of work is created for each of those assets, and none for an
  asset that already has that model's vector

#### Scenario: Asking twice
- **WHEN** an operator asks for the missing work twice, with the first request's
  work still unfinished
- **THEN** no second unit of work is created for the same asset and model

#### Scenario: Two operators ask at the same time
- **WHEN** two requests for the missing work of one model overlap in time
- **THEN** each asset that needed work has exactly one new unit of it, as if the
  two had run one after the other

#### Scenario: An asset whose work already failed
- **WHEN** an operator asks for the missing work and an asset has no vector for
  that model because its work for it failed
- **THEN** no work is created for that asset, and the answer says how many
  assets were passed over for that reason and what runs failed work again

#### Scenario: Nothing queues work by itself
- **WHEN** the service starts with assets that have no vector for an enabled
  model
- **THEN** no work is created until an operator asks for it
