## ADDED Requirements

### Requirement: Analysts Must Be Able To Manage Product Supply-Chain Mappings In The GUI

The platform SHALL provide a desktop GUI workflow that lets an analyst select a company, choose one of its products, and manage upstream and downstream related companies for that product.

Each managed mapping SHALL support:

- source company identity
- source product identity
- direction as upstream or downstream
- related company identity
- relation type
- weight
- rationale or note

#### Scenario: Add an upstream supplier for a product

- **GIVEN** an analyst selects a company and one of its products in the management page
- **WHEN** the analyst adds an upstream company mapping with valid fields and saves it
- **THEN** the platform stores the mapping persistently
- **AND** the saved mapping appears in the current relationship list for that product

#### Scenario: Add a downstream customer for a product

- **GIVEN** an analyst selects a company and one of its products in the management page
- **WHEN** the analyst adds a downstream company mapping and saves it
- **THEN** the platform stores the mapping persistently
- **AND** the mapping is available when the analyst later returns to the page


### Requirement: Managed Product Supply-Chain Mappings Must Persist Across Sessions

The platform SHALL persist analyst-managed product supply-chain mappings so they survive application restarts and can be reloaded in later sessions.

#### Scenario: Reload saved mappings after restart

- **GIVEN** an analyst previously saved product supply-chain mappings
- **WHEN** the application is restarted and the same company/product is opened again
- **THEN** the previously saved mappings are loaded from persistent storage
- **AND** the analyst can continue editing from the saved state


### Requirement: Saved Mappings Must Be Reused As Chain Context

The platform SHALL reuse saved product supply-chain mappings when later configuring related companies so prior work contributes to a visible chain of connected entities.

#### Scenario: Reuse a saved downstream company when editing the next company

- **GIVEN** an analyst saved a downstream mapping from `Company A / Product X` to `Company B`
- **WHEN** the analyst later opens the management page for `Company B`
- **THEN** the platform surfaces the existing relationship context connecting it to `Company A`
- **AND** the analyst can use that context when configuring `Company B`'s own upstream or downstream mappings


### Requirement: Saved Mappings Must Participate In Domino-Effect Analysis

The platform SHALL make saved product supply-chain mappings available to graph exploration and domino-effect analysis flows.

#### Scenario: A saved mapping affects downstream chain analysis

- **GIVEN** an analyst-managed mapping exists between a company's product and a related upstream or downstream company
- **WHEN** the platform builds relationship views or executes domino-effect analysis
- **THEN** the saved mapping is available as part of the relationship context used by those flows
- **AND** the resulting view or analysis can reflect the added chain link


### Requirement: The Editor Must Validate Managed Mappings Before Saving

The platform SHALL reject invalid managed mappings before they are persisted.

Invalid mappings include at least:

- unknown companies
- products not associated with the selected source company
- self-links where the source and related company are the same
- duplicate mappings with the same source company, source product, direction, and related company
- weights outside the accepted range

#### Scenario: Reject a duplicate mapping

- **GIVEN** a mapping already exists for the same source company, source product, direction, and related company
- **WHEN** an analyst attempts to save the same mapping again
- **THEN** the platform rejects the save
- **AND** shows validation feedback describing the duplicate conflict
