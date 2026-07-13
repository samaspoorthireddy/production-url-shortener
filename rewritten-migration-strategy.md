# REST-to-GraphQL Migration Strategy

## The Decision
We will migrate ShopStream's public API from REST to GraphQL—a query language letting clients request exactly the data they need instead of getting a fixed response. This change will reduce frontend (the part of the application users see and interact with) API calls by 40% and eliminate 15 single-purpose endpoints.

## Why We Chose This
Frontend (FE) developers currently waste 30% of each sprint creating custom aggregation endpoints because mobile and web apps require different data shapes from our 47 endpoints. 

We rejected Backend-for-Frontend (BFF) patterns—dedicated services translating between a generic API and specific client apps—due to high operational overhead. Site Reliability Engineering (SRE), the team responsible for keeping services running and performing well, reported that the mobile app makes slow, sequential REST calls. Additionally, the Software Development Kit (SDK) team—who build tools and libraries other developers use to interact with our service—struggles to maintain backwards compatibility across REST versions.

## Timeline and Resources
Three engineers will work full-time on the migration over eight weeks. We will run both APIs concurrently to ensure service continuity. To mitigate the risk of engineers lacking GraphQL experience, the team will pair-program and dedicate learning time during the first two weeks.

## Risks and Mitigations
* **Performance:** The backend team will monitor query performance daily.
* **Caching:** The backend team will implement query depth limits and server-side caching.
* **Timeline:** Project leads may shift the timeline based on implementation findings.
