"""A collection of classes used in the 'machine code' generated by Auto Maple's compiler for each routine."""

import config
import utils
import csv
import settings
from os.path import splitext, basename
from layout import Layout


def update(func):           # TODO: routine keep track of display sequence, don't O(n) every time
    """Decorator function that updates CONFIG.ROUTINE_VAR for all mutative Routine operations."""

    def f(self, *args, **kwargs):
        result = func(self, *args, **kwargs)
        config.gui.set_routine([str(e) for e in self.sequence])
        return result
    return f


class Routine:
    """Describes a routine file in Auto Maple's custom 'machine code'."""

    labels = {}
    index = 0

    def __init__(self):
        self.path = ''
        self.sequence = []

    @update
    def set(self, arr):
        self.sequence = arr

    @update
    def append(self, p):
        self.sequence.append(p)

    def save(self, file_path):
        """Encodes and saves the current Routine at location PATH."""

        result = []
        for item in self.sequence:
            result.append(item.encode())
            if isinstance(item, Point):
                for c in item.commands:
                    result.append(' ' * 4 + c.encode())
        result.append('')

        with open(file_path, 'w') as file:
            file.write('\n'.join(result))

        utils.print_separator()
        print(f"[~] Saved routine to '{basename(file_path)}'.")

    def load(self, file=None):
        """
        Attempts to load FILE into a sequence of Components. If no file path is provided, attempts to
        load the previous routine file.
        :param file:    The file's path.
        :return:        None
        """

        utils.print_separator()
        print(f"[~] Loading routine '{basename(file)}':")

        if not file:
            if self.path:
                file = self.path
                print(' *  File path not provided, using previously loaded routine.')
            else:
                print('[!] File path not provided, no routine was previously loaded either.')
                return False

        ext = splitext(file)[1]
        if ext != '.csv':
            print(f" !  '{ext}' is not a supported file extension.")
            return False

        self.set([])
        Routine.index = 0            # TODO: seq_index can be inside routine
        utils.reset_settings()

        # Compile and Link
        self.compile(file)
        for c in self.sequence:
            if isinstance(c, Jump):
                c.bind()

        self.path = file
        config.gui.view.details.clear_info()
        config.gui.view.status.update_routine(basename(file))
        config.layout = Layout.load(file)
        print(f"[~] Finished loading routine '{basename(splitext(file)[0])}'.")
        return True

    def compile(self, file):
        Routine.labels = {}
        with open(file, newline='') as f:
            csv_reader = csv.reader(f, skipinitialspace=True)
            curr_point = None
            line = 1
            for row in csv_reader:
                result = self._eval(row, line)
                if result:
                    if isinstance(result, Command):
                        if curr_point:
                            curr_point.commands.append(result)
                    else:
                        self.append(result)
                        if isinstance(result, Point):
                            curr_point = result
                line += 1

    def _eval(self, row, i):
        if row and isinstance(row, list):
            first, rest = row[0].lower(), row[1:]
            args, kwargs = utils.separate_args(rest)
            line_error = f' !  Line {i}: '

            if first in SYMBOLS:
                c = SYMBOLS[first]
            elif first in config.command_book:
                c = config.command_book[first]
            else:
                print(line_error + f"Command '{first}' does not exist.")
                return

            try:
                obj = c(*args, **kwargs)
                if isinstance(obj, Label):
                    obj.set_index(len(self))
                    Routine.labels[obj.label] = obj
                return obj
            except (ValueError, TypeError) as e:
                print(line_error + f"Found invalid arguments for '{c.__name__}':")
                print(f"{' ' * 4} -  {e}")

    def __getitem__(self, i):
        return self.sequence[i]

    def __len__(self):
        return len(self.sequence)


#################################
#       Routine Components      #
#################################
class Component:
    id = 'Routine Component'
    PRIMITIVES = {int, str, bool, float}

    def __init__(self, args=None):
        if args is None:
            self._args = {}
        else:
            self._args = args.copy()
            self._args.pop('__class__')
            self._args.pop('self')

    @utils.run_if_enabled
    def execute(self):
        self.main()

    def main(self):
        pass

    def info(self):
        """Returns a dictionary of useful information about this Component."""

        attributes = {}
        for key in self.__dict__:
            if not key.startswith('_'):
                attributes[key] = self.__dict__[key]
        return {
            'name': self.__class__.__name__,
            'vars': attributes
        }

    def encode(self):
        """Encodes an object using its ID and its __init__ arguments."""

        arr = [self.id]
        for key, value in self._args.items():
            if key != 'id' and type(self._args[key]) in Component.PRIMITIVES:
                arr.append(f'{key}={value}')
        return ', '.join(arr)


class Command(Component):
    id = 'Command Superclass'

    def __init__(self, args=None):
        super().__init__(args)
        self.id = self.__class__.__name__

    def __str__(self):
        variables = self.__dict__
        result = '    ' + self.id
        if len(variables) - 1 > 0:
            result += ':'
        for key, value in variables.items():
            if key != 'id':
                result += f'\n        {key}={value}'
        return result


class Point(Component):
    """Represents a location in a user-defined routine."""

    id = '*'

    def __init__(self, x, y, frequency=1, skip='False', adjust='False'):
        super().__init__(locals())
        self.x = float(x)
        self.y = float(y)
        self.location = (self.x, self.y)
        self.frequency = utils.validate_nonzero_int(frequency)
        self.counter = int(utils.validate_boolean(skip))
        self.adjust = utils.validate_boolean(adjust)
        self.commands = []

    def main(self):
        """Executes the set of actions associated with this Point."""

        if self.counter == 0:
            move = config.command_book.get('move')
            move(*self.location).execute()
            if self.adjust:
                adjust = config.command_book.get('adjust')
                adjust(*self.location).execute()
            for command in self.commands:
                command.execute()
        self._increment_counter()

    @utils.run_if_enabled
    def _increment_counter(self):
        """Increments this Point's counter, wrapping back to 0 at the upper bound."""

        self.counter = (self.counter + 1) % self.frequency

    def info(self):
        curr = super().info()
        curr['vars'].pop('location', None)
        curr['vars']['commands'] = ', '.join([c.id for c in self.commands])
        return curr

    def __str__(self):
        return f'  * {self.location}'


class Label(Component):
    id = '@'

    def __init__(self, label):
        super().__init__(locals())
        self.label = str(label)
        if self.label in Routine.labels:
            raise ValueError
        self.links = set()
        self.index = None

    def set_index(self, i):
        self.index = i

    def encode(self):
        return '\n' + super().encode()

    def info(self):
        curr = super().info()
        curr['vars'].pop('links', None)
        return curr

    def __delete__(self, instance):
        del self.links
        Routine.labels.pop(self.label)

    def __str__(self):
        return f'{self.label}:'


class Jump(Component):
    """Jumps to the given Label."""

    id = '>'

    def __init__(self, label, frequency=1, skip='False'):
        super().__init__(locals())
        self.label = str(label)
        self.frequency = utils.validate_nonzero_int(frequency)
        self.counter = int(utils.validate_boolean(skip))
        self.link = None

    def main(self):
        if self.link is None:
            print(f"\n[!] Label '{self.label}' does not exist.")
        else:
            if self.counter == 0:
                Routine.index = self.link.index
            self._increment_counter()

    @utils.run_if_enabled
    def _increment_counter(self):
        self.counter = (self.counter + 1) % self.frequency

    def bind(self):
        """
        Binds this Goto to its corresponding Label. If the Label's index changes, this Goto
        instance will automatically be able to access the updated value.
        :return:    Whether the binding was successful
        """

        if self.label in Routine.labels:
            self.link = Routine.labels[self.label]
            self.link.links.add(self)
            return True
        return False

    def info(self):
        curr = super().info()
        curr['vars'].pop('link', None)
        return curr

    def __delete__(self, instance):
        if self.link is not None:
            self.link.links.remove(self)

    def __str__(self):
        return f'  > {self.label}'


class Setting(Component):
    """Changes the value of the given setting variable."""

    id = '$'

    def __init__(self, key, value):
        super().__init__(locals())
        self.key = str(key)
        if self.key not in settings.SETTING_VALIDATORS:
            raise ValueError(f"Setting '{key}' does not exist")
        self.value = settings.SETTING_VALIDATORS[self.key](value)

    def main(self):
        setattr(settings, self.key, self.value)

    def __str__(self):
        return f'  $ {self.key} = {self.value}'


SYMBOLS = {
    '*': Point,
    '@': Label,
    '>': Jump,
    '$': Setting
}