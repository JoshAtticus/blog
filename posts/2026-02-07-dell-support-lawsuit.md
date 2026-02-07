---
title: Dell support (and hardware) is so bad, I almost sued them 
date: 2026-02-07
tags: General, Hardware, Dell, Support, Warranty, Law, Laptops
---

![Dell XPS 9500 Laptop in warm LED lighting](assets/2025-12-26-dell-support-lawsuit/beat-dell-hero.png)

Yes, you read that title right. Dell's support team is TERRIBLE. They're simply unable to grasp Australian Consumer Law, and I am fed up, but first, some backstory (also apologies for all the red flags):

13 months ago, the 1st of January 2025, I got pissed off enough over the Windows Hello Face Unlock feature on my XPS 9500 not working after a firmware update from Dell killed it. Contacting Dell? Easier said than done. Their support website is a mess, and at the time, after navigating through a labyrinth of "have you tried turning it off and on agains", I was finally at their support page. Just one small problem, the ONLY way you could contact Dell at the time was if you were paying for one of their "Premium Support" extended warranty packages. Didn't buy one? Fuck you, the only option you get is Twitter support.

> For non-Australian readers, this isn't just annoying, it's illegal. Under the Australian Consumer Law, you cannot hide a consumer's statutory right to a remedy behind a paywall.

<!-- <blockquote class="twitter-tweet" data-dnt="true" data-theme="dark"><p lang="en" dir="ltr">I am so fucking tired of <a href="https://twitter.com/Dell?ref_src=twsrc%5Etfw">@Dell</a>&#39;s shitty laptops, I paid around $3k for an XPS 15 back in 2021, and dell gave me probably the worst laptop I have ever used, I have put up with this for long enough, first they released a fault update that broke windows hello permanently (1/5)</p>&mdash; Josh (old account) (@AoshJatticus) <a href="https://twitter.com/AoshJatticus/status/1874351035818664505?ref_src=twsrc%5Etfw">January 1, 2025</a></blockquote> <script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script> -->

[[twitter: https://twitter.com/AoshJatticus/status/1874351035818664505]]

Talking to Dell's Twitter support was no good, which should've been the first red flag. They seemingly didn't care that much, didn't understand what I was saying, before eventually asking to remote into my computer. This took **4 hours**. During these 4 hours, they updated my BIOS (twice, to the same version it was already on), reinstalled my graphics drivers, and tried updating Windows, before eventually opening up a notepad and attempting to gaslight me into thinking my computer does not have face unlock. This absolutely shocked me, and should've been the second red flag, but instead of closing the connection, I took a photo of the sensors, sent it to my laptop and opened it. I also opened Dell's own device configuration page showing I had face unlock. Their reaction? They closed both Windows and ignored me, saying "It's ok" when I attempted to ask them why they tried gaslighting me. Once those 4 hours were up, I was nowhere closer to a working laptop.

After the remote desktop support, Dell asked me for my personal information to schedule a mail-in repair, and 4 days later, I shipped off my laptop. It is extremely important to note for later that I explicitly asked Dell if I could **remove** my SSD and keep it so that it will not be wiped, to which the support agent said I can. The third red flag was when they told me that the depot had received my laptop and was starting work on it, when I literally just shipped it, not just once, they said this four times while the Australia Post app still said it was in my state. 

A week passes, no communication. Fourth red flag. I ask Dell for an update, they don't know where it is. Fifth red flag. I ask them for updates every day, they say they don't know. Week #2, I get a message from Dell asking **me** to send them an SSD. Sixth red flag. I refuse, and ask them to use a test SSD, as replacing the screen should not require an SSD. Week #3 after radio silence from Dell, they tell me they cannot use a test SSD and I must send my personal SSD drive to them for testing. Seventh red flag. I refuse and ask them to send my laptop back. Finally, at week #5, I get my laptop back, once again, not repaired at all.

It's now been 2 months in with an un-fixed laptop, which little did I know, Dell was about to destroy and turn into ewaste. They scheduled an on-site repair through Unisys, to replace not just the screen with the faulty face unlock sensors, but the motherboard too. The repair took about 45 minutes, after which, the technician seemed to be in a rush to leave, and wouldn't let me test the laptop in depth, insisting I signed off. Eighth red flag. Assuming it was fine (it was not), I did. Turns out, the screen that was installed? Bent from the factory. The laptop did not close fully in any orientation, and the LCD panel had highly visible pressure marks on it, but the screen was just the beginning.

It should've stopped right about there. They should've just replaced ONLY the screen, and installed an actually good one. But no, sadly it gets worse. The terribly refurbished motherboard they installed? Failed just **4 days** after installation. I woke up one morning to a completely discharged laptop, despite being plugged in all night. Furthermore, it did not draw any current at all. According to my USB-C PD meter, it negotiated 20V but at 0.0A, drawing 0W. About an hour later, after many different chargers and port combinations, I was able to perform an EC (embedded controller) reset which allowed the laptop to charge again.

Once again, I was back at square one, or should I say, square minus one, because yes they technically fixed face unlock, but now I have a lemon motherboard and a damaged screen, so back to Dell support I go! Hooray! After more pointless troubleshooting, they come to the conclusion that these issues are indeed issues, and agree to a third repair, again onsite. All seems to be going well, the technician tells me that Dell sent them a bent screen, but they'll install it today and follow up with Dell later (ninth red flag), and after the repair, he tells me to contact him if I have any issues. This screen that was installed was still significantly bent and could not close fully, but the marks on the LCD were significantly less visible. 2 weeks pass and I have not received any follow up, and it also happens that exactly 2 weeks after the repair, wouldn't you guess, the shittily refurbished motherboard, fails once again, with the exact, same, issue. 

Back to Dell support, yay! But this time, they were much less friendly. It seems they replaced their real humans with AI, or humans so heavily scripted they might as well be bots. (tenth red flag), because from this point on, Dell's social media support was completely and utterly incompetent, giving very AI sounding answers with zero substance that all translate to "I have no fucking clue what I'm doing and it's your fault". The very first thing they ask for, is my service tag, despite the fact that I literally included my service tag in my message to them. Then, 5 minutes later, they tell me my **warranty has expired**. Eleventh red flag. I respond with something along the lines of "I have an active case under Australian Consumer Law, you are legally required to help me", and 15 minutes later, I get a response from an extremely and overly friendly manager who immediately tells me they will do a 4th repair completely free of cost to me, I just have to reset my laptop and send it in for a mail in repair (twelfth red flag)! I agree, wanting this all over this, I send it in, blah blah blah, 2 weeks pass.

At the end of those 2 weeks, Australia Post decided to be dickheads and told me they'd deliver it 12pm-2pm, so I went out at 10:30am which is when they decided to deliver it, and I had to wait until 4:30pm to collect it from the post office. I was very excited, because at the time I was thinking, "Yes! This is finally over! Dell has finally fixed my laptop, and since it's a mail in repair, they had to have tested it and they can't send it back if it doesn't work," before immediately having all my hopes and dreams shattered when I opened the box. The authorized repair centre (QSL) that Dell hired **completely failed to perform the repair**. Dell is responsible for the quality of their service agents, and this was shockingly poor. Not only did they do NOTHING, they actually DOWNGRADED my laptop, installing a screen with a plastic back panel that does not match the laptop, and did not replace the faulty motherboard, the faulty motherboard which **does not charge** without an EC reset every 24 hours, and even more disgustingly, it was sent back with an unknown white residue which took 20 minutes to remove with a microfibre cloth and isopropyl alcohol.

At this point, I am **fuming** at Dell, this entire time, I have been incredibly polite and incredibly patient with Dell. It has been an absolutely RIDICULOUS amount of time which Dell has WASTED. I was done being the nice guy, and I went straight back to Dell support. I called them out on how they are unable to do their job, that they've wasted months of my time, all for absolutely **nothing**. It was at this point I realised how truly atrocious Dell support was, and when I researched my consumer rights.

Dell attempted to offer a fifth repair multiple times, which I refused, and demanded a refund. What was at first a minor issue under Australian Consumer Law, qualifying for a free repair, turned into a completely non-functional brick by bad repairs. The ANZ Resolutions Manager I was talking to seemed nice at first, but the whole time they were really just stalling to try and waste my time and make me give up. And if you think that's bad? It gets worse.

After my phone call with the Resolutions Manager (who we'll call NA for the rest of this post), NA emailed me asking for videos of my issues. I recorded 3 videos, one showing the USB ports of the laptop disconnecting and reconnecting 8 times in a 2 minute timespan, one showing the face unlock actually no longer functioning after the most recent repair and showing that my dock was fully functional, and one that even the slightest pressure was enough to make the XPS stop working when my MacBook Air worked fine with 3x the force.

Of course, these videos were too long to send via email, so instead, I uploaded them to YouTube, which turned out to reveal just how lazy and deceptive Dell's support team is. I would like to clarify that at this point, it is the 5th of December 2025. I sent the 3 videos as requested by NA. On the 8th of December 2025, NA replies, telling me the Technical Expert team will review them. It was not until the 12th of December that I hear back from NA with an update from the Technical Expert team, with this exact email:

> Hi Josh,
 
> I hope you doing great.
 
> Here are the few question required your answer, i seeking your support to answer it and share it back to me as i will need to update the related team.
> Next action:

> Please get the details to which dock the XPS 9500 is connected?
>There are 2 ports on the left, both not working or just 1?
> Is the dock drivers updated on the system?
> There is 1 port on the right. Is that working as well?
 

> Issue 2: Paint or salt water on the keyboard

> Next action:

> Can we get image of the keyboard for review?

Absolutely, ridiculous. The videos I sent clearly show that this is a hardware failure, and NA is asking me if my dock drivers are updated. They would also see that the dock works fine with other systems if they actually watched the videos I sent them! Speaking of which! Let's check in on those YouTube stats, I can helpfully sort views by views from force.com, which is the Salesforce software I assume Dell uses:

![Video showing face unlock not working, dock working, statistics showing 5 seconds of watch time](assets/2025-12-26-dell-support-lawsuit/Screenshot 2025-12-27 at 10.35.14 PM.png)
![Video showing USB ports disconnecting with slight force, statistics showing 15 seconds of watch time](assets/2025-12-26-dell-support-lawsuit/Screenshot 2025-12-27 at 10.38.17 PM.png)
![Video showing USB ports disconnecting 8 times in 2 minutes with normal typing, statistics showing 1 minute and 5 seconds of watch time](assets/2025-12-26-dell-support-lawsuit/Screenshot 2025-12-27 at 10.39.11 PM.png)

Ahhh, so there's our issue! It took Dell an **entire week** for 2-3 people to watch 85 seconds of video. It also explains why they act so dumb! Because they quite literally are! They watched **five whole seconds** of one of the videos. To be clear: It is physically impossible to diagnose an intermittent connection issue in 5 seconds. This proves they didn't watch the evidence to find a solution; they clicked the link to tick a box and then sent me a template email to stall for time.

And! Not only that, it didn't take them a week to watch it, they watched it 2 days after I sent it! It took them 5 days from watching my evidence to sending me a completely useless template reply to try and stall.

![2 views from force.com on 7 December 2025](assets/2025-12-26-dell-support-lawsuit/Screenshot 2025-12-27 at 10.44.09 PM.png)

And then, I snapped. I realised Dell was wasting my time, wasting their own time, wasting money, just *praying* that I would give up, but I did not. Below is a snippet of my **final** email to Dell, notifying them that I intended to sue them.

> NOTICE OF INTENTION TO SUE:

> I have attempted to resolve this through Dell Support and have lodged a complaint with Consumer Protection WA. However, Dell has explicitly refused my rights in writing.

> If the full refund of $2,939.00 is not confirmed by 5:00 PM AWST on Friday, January 16, 2026, I will commence legal proceedings against Dell Australia Pty Ltd in the Magistrates Court of Western Australia (Minor Case Claim) without further notice.

And what did I get for an entire week? **Radio silence**. No response, they ignored me completely. Well, they probably didn't ignore me *entirely*, legal was probably exploding internally looking at my case going "there's no way we're going to win this, but we'll also probably let this happen anyways because we'll get paid $20k to lose in court from our hourly fees and travel costs anyways". 

Let's go back a few days though, to the 6th of January 2026, when, very surprisingly, I actually got an email from Consumer Protection WA! This is quite surprising to me, because from everything I've heard from people, Consumer Protection WA can't actually do anything useful, and takes forever to give a non-binding verdict. But lo and behold, Consumer Protection WA actually did something useful! I got an email just 1 day after their offices reopened from the New Year break, stating that they had contacted Dell and asked them to contact me about my complaint within 7 days, which brings us back to 2 days later, on the 8th of January 2026.

Remember NA? Somehow they're still involved in this case, despite stating that they would be archiving my case. Well on the 8th of January, I got a phone call from NA, which had quite a few red flags:

- When I picked up the call with the Call Screen feature on my Pixel, they hung up after hearing that the call would be recorded.
- When I called back, they sent my call to voicemail
- They then returned my call 5 minutes later, I noticed that their tone seemed very hushed and quiet. When I got my first call from them, they were in a busy office environment, but this time, it sounded like they were in a completely silent room and whispering as if hiding something
- They told me that "after reviewing my case", they've actually decided to issue me a full refund for "an amount" of money
- It felt like they were trying to keep this 'off the books' or hide it from their own Legal department to avoid a formal audit.

The email I received from NA stated the following:

> Hi Josh,
 
> Thank you for taking the time to speak with me during our recent call.

> As discussed, I kindly request you to share a copy of the invoice as you are the purchaser and we require it for our records.

> Additionally, we will arrange for the collection of the system and proceed with the refund process.
 
> A separate email from our refund team will be sent to you shortly, providing confirmation details and instructions for crediting the funds.

> Please let me know if you have any questions or need further assistance.

To which I replied with:

> Hi NA,

> Thank you for the confirmation.

> As requested, I have attached the original Tax Invoice for your records.

> Further to our phone conversation today and your email below, I accept the offer to return the device on the strict condition that a full refund of $2,939.00 AUD (inclusive of GST) is processed.

> For the avoidance of doubt, I am proceeding based on the following terms:

> Quantum: The refund will be for the full purchase price of $2,939.00 AUD (inclusive of GST). I do not accept any depreciation or usage deductions.

> Purpose: This collection is for the purpose of a Refund Only, not for repair or diagnosis.

> Condition: The device is currently in a non-functional state (Dead PCH/Motherboard) as documented in my previous correspondence and videos. Dell accepts the device in this condition.

> Dispute Status: I will not close my Consumer Protection WA dispute (Ref: [REDACTED]) until the funds have cleared in my bank account.

> Please have the Refund Team send the confirmation email immediately so we can finalise this.

My reasoning for explicitly stating these terms is that I did not trust Dell to not pull a fast one on me. Should they take my laptop and **not** honour these terms, I could sue them for unlawful retention of property and breach of contract, even easier to win than my original case.

So, where does that leave us?

After over 13 months, Dell caved and gave me my full refund of **$2,939.00 AUD** (inclusive of GST) without me having to go to court. While this is the outcome I wanted, we should absolutely NOT ignore that it took a **notice of intention to sue** and a complaint to Consumer Protection WA to get there.

Dell has likely spent approximately **$25,000 AUD** in parts, labour, shipping, legal and administrative time over the last 13 months. They burned through four motherboards, three screens, countless hours of support time, and now they had to pay me the full **A$2,939.00** refund anyway.

All of this could have been avoided if they had simply followed the law in January 2025.

If you are reading this and fighting a similar battle: **Do not give up!**

1.  Document everything

2.  Check your analytics (this is if you've sent links for videos or files such as YouTube, you’d be surprised what they ignore).

3.  Don't be afraid to draft the lawsuit

Corporations rely on you getting tired. They rely on you needing the money *now* so you’ll accept less. But if you hold the line, keep your receipts, and threaten to drag them in front of a Magistrate, the math changes. Suddenly, paying you is the cheapest option they have.

I'm taking my $2,939 and building a custom PC. Dell will never see a cent of my money again. I used to be a huge Dell fan, recommending XPS laptops to everyone, but after this experience, I will be actively discouraging anyone from buying Dell products. I hope this post serves as a warning to others about the potential nightmare of dealing with Dell's support and the importance of knowing your consumer rights.