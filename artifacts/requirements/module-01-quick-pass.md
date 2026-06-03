# Module 1: Quick Pass Requirements

This is a direct-start warm-up artifact capturing initial impressions of the SkillSwap specification.

## 1. Five Explicit Requirements
1. **Browse Service Providers**: Users must be able to browse service providers categorized by their service types (Paragraph 1).
2. **Search Feature**: The search feature must "feel instant" to the user (Paragraph 1).
3. **Set Availability and Pricing**: Providers must be able to set their own availability schedule, pricing rates, and service descriptions (Paragraph 2).
4. **Vetting Process**: There must be a vetting and approval process for new providers before their profiles go live (Paragraph 2 & 3).
5. **Platform Commission**: The platform must automatically deduct a 15% commission fee from transactions (Paragraph 2).

## 2. Two Ambiguities Least Sure About
1. **"Feel Instant" Search**: What are the quantitative thresholds for search speed (e.g. latency under 100ms or 200ms)? What scale of concurrent users and queries must sustain this performance?
2. **"Provider's Cancellation Policy"**: Does the platform provide pre-configured templates for cancellation policies that providers choose from (e.g. 24h notice, 48h notice), or can providers write arbitrary custom rules? How are dispute and refund percentages calculated based on these policies?

## 3. One Critical Question for the PM Right Now
- **Question**: "Does the 15% commission apply universally to all service categories, or do we need to support variable commission rates depending on service category, provider tier, or transaction size?"
