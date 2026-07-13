# Technical Explanation: REST-to-GraphQL Migration

## Decision Summary
ShopStream is migrating its public-facing API from REST to GraphQL over the next eight weeks to streamline front-end data fetching. This migration will solve our platform's layout-dependency issues and eliminate redundant endpoints. By transitioning, we will reduce front-end API calls by 40% and accelerate feature development for the mobile team.

## Why We Chose This
We chose GraphQL to replace REST because GraphQL allows clients to request exactly the data they need in a single request. 

To understand the difference, think of a REST API—which uses specific URLs called endpoints to deliver pre-packaged blocks of data—as a restaurant with a fixed menu. If you order menu item #7, you get whatever is in dish #7, even if you did not want the side salad. 
In contrast, GraphQL acts like a buffet where you pick exactly what you want on your plate and nothing more.

Currently, ShopStream's REST API has 47 endpoints, 15 of which exist solely because the mobile app needs a different data shape than the web app for the same screen. 
Furthermore, our front-end developers spend about 30% of each sprint building custom "aggregation endpoints" to stitch data together from multiple services. 
Transitioning to GraphQL eliminates these single-purpose endpoints and prevents the mobile and web apps from over-fetching or under-fetching data.

We rejected keeping REST and building a Backend-for-Frontend (BFF) service—a dedicated translation layer for each front-end client—because a BFF adds operational complexity by introducing another service to deploy and monitor. 
We also rejected standardizing REST endpoint shapes using a shared schema—a contract or blueprint that defines all the data fields and types our API supports—because it does not resolve the fundamental issue that different front-end clients inherently require different data structures.

## Risks and Mitigations
GraphQL has a steeper learning curve than REST, meaning our engineering team will require time to build expertise. To mitigate this risk, we have assigned three full-time engineers to lead the migration, who will pair-program and share knowledge with team members new to GraphQL.

Nested GraphQL queries can lead to unpredictable query performance if clients request deeply nested relationships. We will mitigate this by implementing query depth limiting and pagination rules on the server.

Caching—saving API responses temporarily so we don't have to fetch them from scratch every time—is harder with GraphQL than with REST because REST uses unique URLs that are easily cached, whereas GraphQL queries use POST requests with query bodies. We will mitigate this by introducing persisted queries—where the server pre-saves query structures so clients only send a short identifier instead of the full query—and using client-side caching libraries to store results.

## What This Means for Priya
As our new backend engineer, Priya will write new schema definitions and GraphQL resolvers—functions on the server that fetch the actual data for specific fields in a query—rather than creating REST routes. Priya will also help migrate our existing web and mobile data models to the new GraphQL endpoint.

During this transition, Priya will support both REST and GraphQL interfaces because both systems will run concurrently for eight weeks.

## Next Steps
Priya will complete the following tasks:
1. Priya will schedule a 30-minute overview session with her onboarding buddy, Alex, by Tuesday afternoon.
2. Priya will read the GraphQL schema definition files located in the `app/schemas/graphql/` directory by Wednesday evening.
3. Priya will complete the first three modules of the GraphQL tutorial at `graphql.org/learn` by Friday afternoon.
4. Priya will clone the repository and run the local development server to test existing queries by Friday evening.
