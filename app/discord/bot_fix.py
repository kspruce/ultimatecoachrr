def fix_bot_class():
    """Fix the UltimateCoachBot class by adding the start_bot method"""
    from app.discord.bot import UltimateCoachBot
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Check if start_bot method exists
    if not hasattr(UltimateCoachBot, 'start_bot'):
        logger.info("Adding start_bot method to UltimateCoachBot class")
        
        def start_bot(self):
            """Start the Discord bot in a separate thread"""
            if not self.token:
                logger.error("Discord bot token not configured")
                return
            
            import threading
            
            def run_bot():
                try:
                    import asyncio
                    asyncio.run(self.bot.start(self.token))
                except Exception as e:
                    logger.error(f"Error starting Discord bot: {str(e)}")
                    logger.exception(e)
            
            bot_thread = threading.Thread(target=run_bot, daemon=True)
            bot_thread.start()
            logger.info("Discord bot started in background thread")
        
        # Add the method to the class
        UltimateCoachBot.start_bot = start_bot
        logger.info("start_bot method added to UltimateCoachBot class")
    else:
        logger.info("start_bot method already exists in UltimateCoachBot class")
