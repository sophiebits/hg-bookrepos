import errno

from mercurial import bookmarks
from mercurial import commands
from mercurial import encoding
from mercurial import hg
from mercurial import node
from mercurial import util


def _read_bookmark(repo):
    """Return the name of the remote branch that the repo is tracking."""
    # Based on bookmarks.readcurrent
    try:
        file = repo.opener('bookrepos.bookmark')
    except IOError, inst:
        if inst.errno != errno.ENOENT:
            raise
        raise util.Abort("missing bookmark file")
    try:
        # No readline() in posixfile_nt, reading everything is cheap
        mark = encoding.tolocal((file.readlines() or [''])[0])
        if mark:
            return mark
        else:
            raise util.Abort("can't read bookmark file")
    finally:
        file.close()


def _set_bookmark(repo, mark):
    """Set the name of the remote branch that the repo is tracking."""
    # Based on bookmarks.setcurrent
    wlock = repo.wlock()
    try:
        file = repo.opener('bookrepos.bookmark', 'w', atomictemp=True)
        file.write(encoding.fromlocal(mark))
        file.close()
    finally:
        wlock.release()


def kclone(ui, source, bookmark, dest=None):
    """Clone the source repo at the specified bookmark."""
    r = hg.clone(ui, peeropts={}, source=source, dest=dest, rev=[bookmark])
    if r is None:
        return 1
    srcrepo, destrepo = r

    # Clear any bookmarks that were carried over. We don't want or need them.
    destrepo._bookmarks.clear()
    bookmarks.write(destrepo)

    # Save the bookmark that we're tracking so that we can use it later
    _set_bookmark(destrepo, bookmark)


def kpull(ui, repo, bookmark=None):
    """Pull the changes from the specified remote bookmark into the local
    repository.
    """
    if bookmarks.listbookmarks(repo):
        raise util.Abort("local repo must not have any bookmarks")

    bookmark = _read_bookmark(repo) if bookmark is None else bookmark
    return commands.pull(ui, repo, source='default', rev=[bookmark])


def kpush(ui, repo, bookmark=None, force=False, new_bookmark=False, **opts):
    """Push the current changeset (.) to the specified bookmark on the default
    push remote.

    Returns 0 if push was successful, 1 on error.
    """
    if bookmarks.listbookmarks(repo):
        raise util.Abort("local repo must not have any bookmarks")

    # First, push the changeset
    dest = ui.expandpath('default-push', 'default')
    dest, _ = hg.parseurl(dest)
    ui.status("pushing to %s\n" % util.hidepassword(dest))

    remote = hg.peer(repo, opts, dest)
    head = repo['.']

    # Push subrepos, copied from commands.push
    # TODO(alpert): What is this _subtoppath craziness?
    repo._subtoppath = dest
    try:
        # Push subrepos depth-first for coherent ordering
        subs = head.substate  # Only repos that are committed
        for s in sorted(subs):
            if head.sub(s).push(opts) == 0:
                return False
    finally:
        del repo._subtoppath

    result = repo.push(remote, force, revs=[head.node()])
    result = not result  # Uh, okay...

    # Then, update the bookmark
    bookmark = _read_bookmark(repo) if bookmark is None else bookmark
    remote_books = remote.listkeys('bookmarks')
    new_node = node.hex(repo.lookup('.'))

    if bookmark in remote_books:
        old_node = remote_books[bookmark]
        if new_node == old_node:
            ui.status("nothing to update\n")
            return 0
        elif repo[new_node] in repo[old_node].descendants():
            ui.status("updating bookmark %s\n" % bookmark)
        elif force:
            ui.status("force-updating bookmark %s\n" % bookmark)
        else:
            ui.warn("skipping non-fast-forward update of bookmark %s\n" %
                    bookmark)
            return 1
    elif new_bookmark:
        old_node = ''
        ui.status("creating bookmark %s\n" % bookmark)
    else:
        ui.warn('remote bookmark %r not found: did you want --new-bookmark?\n'
                % bookmark)
        return 1

    r = remote.pushkey('bookmarks', bookmark, old_node, new_node)
    if not r:
        # Either someone else pushed at the same time as us or new_node doesn't
        # exist in the remote repo (see bookmarks.pushbookmark).
        ui.warn("updating bookmark %s failed!\n" % bookmark)
        return 1

    return 0

cmdtable = {
    'kclone':
    (kclone,
     [],
     'SOURCE BOOKMARK [DEST]'),

    'kpull':
    (kpull,
     [],
     '[BOOKMARK]'),

    'kpush':
    (kpush,
     [('f', 'force', False, 'allow non-fast-forward pushes'),
      ('', 'new-bookmark', False, 'allow pushing a new bookmark')],
     '[--new-bookmark] [BOOKMARK]'),
    }
commands.norepo += ' kclone'

testedwith = '2.2.3'
