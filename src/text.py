no_poll_in_channel = "this channel doesn't have a poll running"
cant_find_poll = "sorry, I cannot find a poll with that id, please try again"
poll_now_closed = "The poll has now been closed."
confirm_end_poll = "Are you sure you want to end this poll?\nNo more votes "\
                   "will be able to be cast and the results will be "\
                   "calculated, to, proceed, reply `yes` to stop, type `no`"
confirm_vote = "Respond with a `yes` if your vote is correct or respond with "\
               ""\
               "a `no` if it is not. \nYour vote:"
invalid_vote_option = "that option doesnt exist, please try again"
timeout = "Two minute timeout reached, please enter the original command again"
vote_processed = "your vote has been processed"
vote_not_processed = "your vote has not been processed, please try again"
not_enough_options = "there are less than two options for people to vote "\
                     "on!\n\nHere are the current options:\n\n"
poll_already_started = "this poll has already started"
poll_already_ended = "this poll has already ended"
poll_not_started = "this poll has not started yet"
cannot_convert_to_int = "there was an error converting a string to an integer"
cannot_vote_poll_closed = "this poll is not open, it either must first be "\
                          "started before voting, or this poll has ended"
already_voted = "it looks like you already voted"
add_option_wrong_format = "you passed the incorrect number of parameters"
invalid_poll_type = "That isn't a valid poll type, please try again"
only_mention_one = "You must mention exactly one person per command"
option_already_exists = "that option already exists"
stv_submit_text = "To vote in this poll, rank the available options starting "\
                  "at 1, copy and paste the following, and replace the <x>s "\
                  "with your ranking (or leave the <x>s there if you dont "\
                  "want to rank them):"


def account_age(user_age, required_age):
    return ("this discord account is " + str(
        user_age) + " days old, your account must be at least " +
            str(required_age) + " days old.")
